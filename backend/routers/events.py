
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Event, Venue
from backend.schemas import EventCreate, EventResponse
from backend.security import require_role

router = APIRouter(
    prefix="/events",
    tags=["Event Management"]
)


# View all active events
@router.get("/", response_model=list[EventResponse])
def get_events(db: Session = Depends(get_db)):
    return db.query(Event).filter(
        Event.status == "active"
    ).all()


# Create event - Admin only
@router.post("/", response_model=EventResponse)
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin"))
):
    if event_data.start_at >= event_data.end_at:
        raise HTTPException(
            status_code=400,
            detail="Event end time must be after start time"
        )

    venue = db.query(Venue).filter(
        Venue.id == event_data.venue_id,
        Venue.is_active == True
    ).first()

    if not venue:
        raise HTTPException(
            status_code=404,
            detail="Active venue not found"
        )

    if event_data.total_tickets > venue.capacity:
        raise HTTPException(
            status_code=400,
            detail="Tickets cannot exceed venue capacity"
        )

    existing_events = db.query(Event).filter(
        Event.venue_id == venue.id,
        Event.status == "active"
    ).all()

    buffer_time = timedelta(
        minutes=venue.turnaround_minutes
    )

    for existing in existing_events:
        if (
            event_data.start_at < existing.end_at + buffer_time
            and event_data.end_at > existing.start_at - buffer_time
        ):
            raise HTTPException(
                status_code=409,
                detail="Venue is unavailable during this time"
            )

    new_event = Event(
        title=event_data.title,
        description=event_data.description,
        category=event_data.category,
        venue_id=event_data.venue_id,
        start_at=event_data.start_at,
        end_at=event_data.end_at,
        ticket_price=event_data.ticket_price,
        total_tickets=event_data.total_tickets,
        created_by=current_user.id,
        status="active"
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return new_event
