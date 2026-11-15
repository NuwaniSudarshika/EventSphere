
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import Booking, Event, Ticket
from backend.schemas import BookingCreate, BookingResponse
from backend.security import require_role

router = APIRouter(prefix="/bookings", tags=["Booking Management"])


@router.post("/", response_model=BookingResponse, status_code=201)
def create_booking(
    booking_data: BookingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    event = db.query(Event).filter(
        Event.id == booking_data.event_id,
        Event.status == "active"
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if booking_data.quantity < 1:
        raise HTTPException(status_code=400, detail="Invalid ticket quantity")

    confirmed = db.query(
        func.coalesce(func.sum(Booking.quantity), 0)
    ).filter(
        Booking.event_id == event.id,
        Booking.status == "confirmed"
    ).scalar()

    available = event.total_tickets - confirmed

    if booking_data.quantity > available:
        raise HTTPException(
            status_code=400,
            detail=f"Only {available} tickets available"
        )

    booking = Booking(
        user_id=current_user.id,
        event_id=event.id,
        quantity=booking_data.quantity,
        total_amount=event.ticket_price * booking_data.quantity,
        status="confirmed",
        payment_reference="SIM-" + uuid4().hex[:12].upper()
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Automatically request ticket generation from TicketAgent
    try:
        from backend.agents.message_bus import send_message

        send_message(
            db,
            sender="BookingAgent",
            receiver="TicketAgent",
            performative="REQUEST",
            content={"action": "GENERATE_TICKETS", "booking_id": booking.id},
            conversation_id=f"booking-{booking.id}"
        )
    except Exception as error:
        print("Ticket agent request failed:", error)

    return booking


@router.get("/my-bookings", response_model=list[BookingResponse])
def get_my_bookings(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    return db.query(Booking).filter(
        Booking.user_id == current_user.id
    ).order_by(Booking.created_at.desc()).all()


@router.post("/cancel/{booking_id}")
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.user_id == current_user.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Only confirmed bookings can be cancelled"
        )

    booking.status = "cancelled"

    # Cancel tickets belonging to this booking
    tickets = db.query(Ticket).filter(
        Ticket.booking_id == booking.id
    ).all()

    for ticket in tickets:
        ticket.status = "cancelled"

    refund_reference = "REF-" + uuid4().hex[:12].upper()

    db.commit()

    return {
        "message": "Booking cancelled successfully",
        "booking_id": booking.id,
        "refund_amount": booking.total_amount,
        "refund_reference": refund_reference,
        "payment_type": "Simulated refund"
    }
