
import uuid
import qrcode
import base64
from io import BytesIO
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Booking, Ticket, Event
from backend.schemas import TicketResponse, CheckInRequest
from backend.security import require_role

router = APIRouter(
    prefix="/tickets",
    tags=["Ticket Management"]
)


# Generate tickets after confirmed booking
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

    for _ in range(booking.quantity):
        ticket = Ticket(
            booking_id=booking.id,
            ticket_code=uuid.uuid4().hex.upper(),
            qr_token=uuid.uuid4().hex + uuid.uuid4().hex,
            status="valid"
        )
        db.add(ticket)
        tickets.append(ticket)

    db.commit()

    for ticket in tickets:
        db.refresh(ticket)

    return tickets


# View attendee's tickets
@router.get("/my-tickets", response_model=list[TicketResponse])
def get_my_tickets(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("attendee"))
):
    bookings = db.query(Booking).filter(
        Booking.user_id == current_user.id
    ).all()

    booking_ids = [b.id for b in bookings]

    return db.query(Ticket).filter(
        Ticket.booking_id.in_(booking_ids)
    ).all()


# Staff check-in
@router.post("/check-in")
def check_in_ticket(
    ticket_data: CheckInRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("staff"))
):
    ticket = db.query(Ticket).filter(
        (Ticket.ticket_code == ticket_data.ticket_code) |
        (Ticket.qr_token == ticket_data.ticket_code)
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Invalid ticket"
        )

    if ticket.status != "valid":
        raise HTTPException(
            status_code=400,
            detail="Ticket already used or cancelled"
        )

    booking = db.query(Booking).filter(
        Booking.id == ticket.booking_id
    ).first()

    event = db.query(Event).filter(
        Event.id == booking.event_id
    ).first()

    now = datetime.utcnow()

    if now < event.start_at or now > event.end_at:
        raise HTTPException(
            status_code=400,
            detail="Check-in is outside the event time window"
        )

    ticket.status = "used"
    ticket.checked_in_at = now
    ticket.checked_in_by = current_user.id

    db.commit()

    return {
        "message": "Check-in successful",
        "ticket_code": ticket.ticket_code
    }


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
        "qr_image": encoded
    }
