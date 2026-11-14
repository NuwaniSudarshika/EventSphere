
from fastapi import FastAPI

app = FastAPI(
    title="EventSphere",
    description="Multi-Agent Event and Venue Booking System",
    version="1.0.0"
)


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
