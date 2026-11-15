
import secrets

from sqlalchemy.orm import Session

from backend.models import Booking, Ticket
from backend.agents.message_bus import (
    send_message,
    save_agent_state
)


class TicketAgent:

    def __init__(self):
        self.name = "TicketAgent"
        self.goal = "Generate unique tickets and QR tokens"

    def handle_message(self, db: Session, message):

        content = message.content or {}

        # 1. Validate action
        action = content.get("action")

        if action not in (None, "GENERATE_TICKETS"):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Unknown ticket action"},
                message.conversation_id
            )

        # 2. Validate booking ID
        booking_id = content.get("booking_id")

        if not isinstance(booking_id, int) or isinstance(booking_id, bool) or booking_id <= 0:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid booking ID"},
                message.conversation_id
            )

        # 3. Find confirmed booking
        booking = db.query(Booking).filter(
            Booking.id == booking_id,
            Booking.status == "confirmed"
        ).first()

        if not booking:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Valid confirmed booking not found"},
                message.conversation_id
            )

        # 4. Validate optional booking details
        requested_user_id = content.get("user_id")
        requested_event_id = content.get("event_id")
        requested_quantity = content.get("quantity")

        if requested_user_id is not None and requested_user_id != booking.user_id:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Booking user mismatch"},
                message.conversation_id
            )

        if requested_event_id is not None and requested_event_id != booking.event_id:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Booking event mismatch"},
                message.conversation_id
            )

        if requested_quantity is not None and requested_quantity != booking.quantity:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Booking quantity mismatch"},
                message.conversation_id
            )

        # 5. Prevent duplicate ticket generation
        existing_tickets = db.query(Ticket).filter(
            Ticket.booking_id == booking.id
        ).count()

        if existing_tickets > 0:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {
                    "reason": "Tickets already generated",
                    "existing_ticket_count": existing_tickets
                },
                message.conversation_id
            )

        generated_tickets = []

        try:
            # 6. Generate unique ticket codes and QR tokens
            for _ in range(booking.quantity):

                ticket_code = "TKT-" + secrets.token_urlsafe(16)
                qr_token = secrets.token_urlsafe(32)

                new_ticket = Ticket(
                    booking_id=booking.id,
                    ticket_code=ticket_code,
                    qr_token=qr_token,
                    status="valid"
                )

                db.add(new_ticket)

                generated_tickets.append({
                    "ticket_code": ticket_code,
                    "qr_token": qr_token
                })

            # 7. Commit tickets
            db.commit()

            # 8. Save agent state
            save_agent_state(
                db,
                self.name,
                {
                    "last_booking_id": booking.id,
                    "last_event_id": booking.event_id,
                    "tickets_generated": len(generated_tickets),
                    "last_status": "completed"
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db, self.name, message.sender, "FAILURE",
                {"reason": "Ticket generation failed"},
                message.conversation_id
            )

        # 9. Inform requesting agent
        return send_message(
            db,
            self.name,
            message.sender,
            "INFORM",
            {
                "booking_id": booking.id,
                "ticket_count": len(generated_tickets),
                "tickets": generated_tickets,
                "status": "success",
                "message": "Tickets generated successfully"
            },
            message.conversation_id
        )
