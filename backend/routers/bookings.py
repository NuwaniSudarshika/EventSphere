
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Event, Booking
from backend.schemas import BookingCreate, BookingResponse
from backend.security import require_role

router = APIRouter(
    prefix="/bookings",
    tags=["Booking Management"]
)


@router.post("/", response_model=BookingResponse)
def create_booking(
    booking_data: BookingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    event = db.query(Event).filter(
        Event.id == booking_data.event_id,
        Event.status == "active"
    ).with_for_update().first()

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    if booking_data.quantity > event.total_tickets:
        raise HTTPException(
            status_code=400,
            detail="Invalid ticket quantity"
        )

    booked_tickets = db.query(Booking).filter(
        Booking.event_id == event.id,
        Booking.status == "confirmed"
    ).with_entities(
        Booking.quantity
    ).all()

    already_booked = sum(item[0] for item in booked_tickets)

    available_tickets = event.total_tickets - already_booked

    if booking_data.quantity > available_tickets:
        raise HTTPException(
            status_code=400,
            detail="Not enough tickets available"
        )

    total_amount = event.ticket_price * booking_data.quantity

    payment_reference = "SIM-" + uuid.uuid4().hex[:12].upper()

    new_booking = Booking(
        user_id=current_user.id,
        event_id=event.id,
        quantity=booking_data.quantity,
        total_amount=total_amount,
        status="confirmed",
        payment_reference=payment_reference
    )

    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    return new_booking


@router.get("/my-bookings", response_model=list[BookingResponse])
def get_my_bookings(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    return db.query(Booking).filter(
        Booking.user_id == current_user.id
    ).all()
