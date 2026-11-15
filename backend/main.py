
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.routers import (
    auth,
    venues,
    events,
    bookings,
    tickets,
    agents
)

from backend.agents.dispatcher import (
    run_message_listener,
    run_waitlist_timer
)


templates = Jinja2Templates(
    directory="backend/templates"
)


@asynccontextmanager
async def lifespan(app: FastAPI):

    stop_event = asyncio.Event()

    listener_task = asyncio.create_task(
        run_message_listener(stop_event)
    )

    waitlist_timer_task = asyncio.create_task(
        run_waitlist_timer(stop_event)
    )

    print("EventSphere Background Tasks Started")

    yield

    stop_event.set()

    listener_task.cancel()
    waitlist_timer_task.cancel()

    for task in [listener_task, waitlist_timer_task]:
        try:
            await task
        except asyncio.CancelledError:
            pass

    print("EventSphere Background Tasks Stopped")


app = FastAPI(
    title="EventSphere",
    description="Multi-Agent Event and Venue Booking System",
    version="1.0.0",
    lifespan=lifespan
)


app.mount(
    "/static",
    StaticFiles(directory="backend/static"),
    name="static"
)


# API Routers
app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(bookings.router)
app.include_router(tickets.router)
app.include_router(agents.router)


# Home Page
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


# Login Page
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )


# Register Page
@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html"
    )


@app.get("/browse-events")
def browse_events_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="events.html"
    )


@app.get("/my-bookings")
def my_bookings_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="my-bookings.html"
    )


@app.get("/venue-hire")
def venue_hire_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="venue-hire.html"
    )



# Health Check
@app.get("/health")
def health():
    return {"status": "healthy"}
