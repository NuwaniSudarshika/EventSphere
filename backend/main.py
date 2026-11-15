
import asyncio

from contextlib import asynccontextmanager
from fastapi import FastAPI

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


@asynccontextmanager
async def lifespan(app: FastAPI):

    stop_event = asyncio.Event()

    # Start Agent Listener
    listener_task = asyncio.create_task(
        run_message_listener(stop_event)
    )

    # Start Waitlist Automatic Timer
    waitlist_timer_task = asyncio.create_task(
        run_waitlist_timer(stop_event)
    )

    print("EventSphere Agent Listener Started")
    print("Waitlist Automatic Timer Started")

    yield

    # Stop background tasks
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


# Register API routers
app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(bookings.router)
app.include_router(tickets.router)
app.include_router(agents.router)


@app.get("/")
def home():

    return {
        "message": "Welcome to EventSphere!",
        "status": "running"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }
