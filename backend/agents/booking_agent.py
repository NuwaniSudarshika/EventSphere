
import uuid
from sqlalchemy.orm import Session

from backend.models import Event, Booking
from backend.agents.message_bus import (
    send_message,
    save_agent_state
)


class BookingAgent:

    def __init__(self):
        self.name = "BookingAgent"
        self.goal = "Process event ticket bookings safely"

    def handle_message(self, db: Session, message):

        content = message.content

        user_id = content.get("user_id")
        event_id = content.get("event_id")
        quantity = content.get("quantity", 0)

        # 1. Validate user ID
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            return send_message(
                db,
                self.name,
                message.sender,
                "REFUSE",
                {"reason": "Invalid user ID"},
                message.conversation_id
            )

        # 2. Validate event ID
        if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0:
            return send_message(
                db,
                self.name,
                message.sender,
                "REFUSE",
                {"reason": "Invalid event ID"},
                message.conversation_id
            )

        # 3. Validate ticket quantity
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            return send_message(
                db,
                self.name,
                message.sender,
                "REFUSE",
                {"reason": "Invalid ticket quantity"},
                message.conversation_id
            )

        # 4. Find active event
        event = db.query(Event).filter(
            Event.id == event_id,
            Event.status == "active"
        ).first()

        if not event:
            return send_message(
                db,
                self.name,
                message.sender,
                "REFUSE",
                {"reason": "Event not found or inactive"},
                message.conversation_id
            )

        # 5. Check available tickets
        bookings = db.query(Booking).filter(
            Booking.event_id == event_id,
            Booking.status == "confirmed"
        ).all()

        booked_count = sum(
            booking.quantity for booking in bookings
        )

        available = event.total_tickets - booked_count

        if quantity > available:
            return send_message(
                db,
                self.name,
                message.sender,
                "REFUSE",
                {
                    "reason": "Not enough tickets available",
                    "available_tickets": max(available, 0)
                },
                message.conversation_id
            )

        # 6. Calculate booking amount
        total_amount = event.ticket_price * quantity

        # 7. Generate simulated payment reference
        payment_reference = (
            "SIM-" + uuid.uuid4().hex[:12].upper()
        )

        # 8. Create booking
        new_booking = Booking(
            user_id=user_id,
            event_id=event_id,
            quantity=quantity,
            total_amount=total_amount,
            status="confirmed",
            payment_reference=payment_reference
        )

        try:
            db.add(new_booking)
            db.commit()
            db.refresh(new_booking)

            booking_id = new_booking.id

            # 9. Save BookingAgent state
            save_agent_state(
                db,
                self.name,
                {
                    "last_booking_id": booking_id,
                    "last_event_id": event_id,
                    "last_user_id": user_id,
                    "last_quantity": quantity,
                    "last_status": "confirmed"
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db,
                self.name,
                message.sender,
                "FAILURE",
                {"reason": "Booking could not be saved"},
                message.conversation_id
            )

        # 10. Send JSON REQUEST to TicketAgent
        try:
            send_message(
                db,
                self.name,
                "TicketAgent",
                "REQUEST",
                {
                    "booking_id": booking_id,
                    "user_id": user_id,
                    "event_id": event_id,
                    "quantity": quantity
                },
                message.conversation_id
            )

        except Exception:
            # Booking is already confirmed.
            # Ticket generation can be retried separately.
            return send_message(
                db,
                self.name,
                message.sender,
                "INFORM",
                {
                    "booking_id": booking_id,
                    "status": "confirmed",
                    "ticket_generation_status": "pending",
                    "total_amount": total_amount,
                    "payment_reference": payment_reference
                },
                message.conversation_id
            )

        # 11. Inform original sender about successful booking
        return send_message(
            db,
            self.name,
            message.sender,
            "INFORM",
            {
                "booking_id": booking_id,
                "status": "confirmed",
                "quantity": quantity,
                "total_amount": total_amount,
                "payment_reference": payment_reference,
                "ticket_generation_status": "requested"
            },
            message.conversation_id
        )
