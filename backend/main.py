
from fastapi import FastAPI

from backend.routers import auth

from backend.routers import venues

app = FastAPI(
    title="EventSphere",
    description="Multi-Agent Event and Venue Booking System",
    version="1.0.0"
)

# Authentication router
app.include_router(auth.router)
app.include_router(venues.router)


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
