
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Venue
from backend.schemas import VenueCreate, VenueResponse
from backend.security import require_role

router = APIRouter(
    prefix="/venues",
    tags=["Venue Management"]
)


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
