
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Venue, VenueHireRequest, AgentMessage
from backend.schemas import VenueCreate, VenueResponse
from backend.security import require_role

from backend.agents.message_bus import send_message
from backend.agents.dispatcher import process_pending_messages


router = APIRouter(
    prefix="/venues",
    tags=["Venue Management"]
)


# Private venue hire request schema
class VenueHireCreate(BaseModel):
    venue_id: int
    start_at: datetime
    end_at: datetime
    expected_attendees: int = Field(gt=0)
    purpose: str = Field(min_length=3, max_length=500)


# View all active venues
@router.get("/", response_model=list[VenueResponse])
def get_venues(db: Session = Depends(get_db)):

    return db.query(Venue).filter(
        Venue.is_active == True
    ).all()


# Create a venue - Admin only
@router.post("/", response_model=VenueResponse)
def create_venue(
    venue_data: VenueCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin"))
):

    new_venue = Venue(
        name=venue_data.name,
        location=venue_data.location,
        capacity=venue_data.capacity,
        turnaround_minutes=venue_data.turnaround_minutes,
        description=venue_data.description
    )

    db.add(new_venue)
    db.commit()
    db.refresh(new_venue)

    return new_venue


# Submit private venue hire request
@router.post("/hire-request")
def create_hire_request(
    request_data: VenueHireCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):

    if request_data.start_at >= request_data.end_at:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time"
        )

    venue = db.query(Venue).filter(
        Venue.id == request_data.venue_id,
        Venue.is_active == True
    ).first()

    if not venue:
        raise HTTPException(
            status_code=404,
            detail="Venue not found"
        )

    if request_data.expected_attendees > venue.capacity:
        raise HTTPException(
            status_code=400,
            detail="Expected attendees exceed venue capacity"
        )

    # Send request to VenueAgent through JSON message bus
    conversation_id = __import__("uuid").uuid4().hex

    try:

        send_message(
            db,
            "API",
            "VenueAgent",
            "REQUEST",
            {
                "action": "HIRE_REQUEST",
                "user_id": current_user.id,
                "venue_id": request_data.venue_id,
                "start_at": request_data.start_at.isoformat(),
                "end_at": request_data.end_at.isoformat(),
                "expected_attendees": request_data.expected_attendees,
                "purpose": request_data.purpose
            },
            conversation_id
        )

        # Process the request immediately
        process_pending_messages(db)

        # Retrieve VenueAgent response
        response = db.query(AgentMessage).filter(
            AgentMessage.sender == "VenueAgent",
            AgentMessage.conversation_id == conversation_id
        ).order_by(
            AgentMessage.id.desc()
        ).first()

        if not response:
            return {
                "status": "pending",
                "conversation_id": conversation_id,
                "message": "Your venue request is being processed."
            }

        return {
            "status": response.performative,
            "conversation_id": conversation_id,
            "result": response.content
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not process venue hire request"
        )


# View attendee's own venue hire requests
@router.get("/my-hire-requests")
def get_my_hire_requests(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):

    requests = db.query(VenueHireRequest).filter(
        VenueHireRequest.user_id == current_user.id
    ).order_by(
        VenueHireRequest.created_at.desc()
    ).all()

    return requests


# Admin can view all venue hire requests
@router.get("/hire-requests")
def get_all_hire_requests(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin"))
):

    return db.query(VenueHireRequest).order_by(
        VenueHireRequest.created_at.desc()
    ).all()
