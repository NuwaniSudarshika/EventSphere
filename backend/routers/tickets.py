
import uuid
import qrcode
import base64

from io import BytesIO
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import update

from backend.database import get_db
from backend.models import Booking, Ticket, Event
from backend.schemas import TicketResponse, CheckInRequest
from backend.security import require_role


router = APIRouter(
    prefix="/tickets",
    tags=["Ticket Management"]
)


# Generate unique QR tickets for confirmed bookings
@router.post("/generate/{booking_id}", response_model=list[TicketResponse])
def generate_tickets(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin"))
):
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.status == "confirmed"
    ).first()

    if not booking:
        raise HTTPException(
            status_code=404,
            detail="Confirmed booking not found"
        )

    existing = db.query(Ticket).filter(
        Ticket.booking_id == booking_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Tickets already generated"
        )

    tickets = []

    try:
        for _ in range(booking.quantity):
            ticket = Ticket(
                booking_id=booking.id,
                ticket_code="TKT-" + uuid.uuid4().hex.upper(),
                qr_token=uuid.uuid4().hex + uuid.uuid4().hex,
                status="valid"
            )

            db.add(ticket)
            tickets.append(ticket)

        db.commit()

        for ticket in tickets:
            db.refresh(ticket)

        return tickets

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Ticket generation failed"
        )


# Attendee can view their own tickets
@router.get("/my-tickets", response_model=list[TicketResponse])
def get_my_tickets(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    return db.query(Ticket).join(
        Booking,
        Ticket.booking_id == Booking.id
    ).filter(
        Booking.user_id == current_user.id
    ).all()


# Staff check-in
@router.post("/check-in")
def check_in_ticket(
    ticket_data: CheckInRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("staff"))
):
    scanned_value = ticket_data.ticket_code.strip()

    if not scanned_value:
        raise HTTPException(
            status_code=400,
            detail="Ticket code is required"
        )

    ticket = db.query(Ticket).filter(
        (Ticket.ticket_code == scanned_value) |
        (Ticket.qr_token == scanned_value)
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Invalid ticket"
        )

    booking = db.query(Booking).filter(
        Booking.id == ticket.booking_id
    ).first()

    if not booking:
        raise HTTPException(
            status_code=404,
            detail="Booking not found"
        )

    if booking.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Booking is cancelled or not confirmed"
        )

    event = db.query(Event).filter(
        Event.id == booking.event_id
    ).first()

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    now = datetime.utcnow()

    if now < event.start_at or now > event.end_at:
        raise HTTPException(
            status_code=400,
            detail="Check-in is outside the event time window"
        )

    # Atomic update prevents two staff members from
    # checking in the same ticket simultaneously.
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket.id,
            Ticket.status == "valid"
        )
        .values(
            status="used",
            checked_in_at=now,
            checked_in_by=current_user.id
        )
        .execution_options(synchronize_session=False)
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ticket already used or cancelled"
        )

    db.commit()

    return {
        "message": "Check-in successful",
        "ticket_code": ticket.ticket_code,
        "event_id": event.id,
        "event_title": event.title,
        "checked_in_at": now.isoformat(),
        "checked_in_by": current_user.id
    }


# Generate QR image for attendee's own ticket
@router.get("/qr/{ticket_id}")
def get_ticket_qr(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    ticket = db.query(Ticket).join(
        Booking,
        Ticket.booking_id == Booking.id
    ).filter(
        Ticket.id == ticket_id,
        Booking.user_id == current_user.id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found"
        )

    qr = qrcode.make(ticket.qr_token)

    buffer = BytesIO()
    qr.save(buffer, format="PNG")

    encoded = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return {
        "ticket_id": ticket.id,
        "ticket_code": ticket.ticket_code,
        "status": ticket.status,
        "qr_image": encoded
    }
