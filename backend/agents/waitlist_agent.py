
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.models import Event, Booking, WaitlistEntry
from backend.agents.message_bus import (
    send_message,
    save_agent_state
)


class WaitlistAgent:

    def __init__(self, hold_minutes=10):
        self.name = "WaitlistAgent"
        self.goal = "Manage event waitlists and temporary ticket holds"
        self.hold_minutes = hold_minutes

    def handle_message(self, db: Session, message):

        content = message.content
        action = content.get("action")

        if action == "JOIN":
            return self.join_waitlist(db, message)

        if action == "RELEASE":
            return self.offer_available_tickets(db, message)

        if action == "CONFIRM":
            return self.confirm_hold(db, message)

        return send_message(
            db,
            self.name,
            message.sender,
            "REFUSE",
            {"reason": "Unknown waitlist action"},
            message.conversation_id
        )

    # --------------------------------------------------
    # 1. JOIN WAITLIST
    # --------------------------------------------------

    def join_waitlist(self, db: Session, message):

        content = message.content

        user_id = content.get("user_id")
        event_id = content.get("event_id")
        quantity = content.get("quantity", 1)

        if (
            not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid user ID"},
                message.conversation_id
            )

        if (
            not isinstance(event_id, int)
            or isinstance(event_id, bool)
            or event_id <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid event ID"},
                message.conversation_id
            )

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or quantity <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid ticket quantity"},
                message.conversation_id
            )

        event = db.query(Event).filter(
            Event.id == event_id,
            Event.status == "active"
        ).first()

        if not event:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Event not found or inactive"},
                message.conversation_id
            )

        existing = db.query(WaitlistEntry).filter(
            WaitlistEntry.user_id == user_id,
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.status.in_(["waiting", "offered"])
        ).first()

        if existing:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Already registered in this event waitlist"},
                message.conversation_id
            )

        entry = WaitlistEntry(
            user_id=user_id,
            event_id=event_id,
            quantity=quantity,
            status="waiting"
        )

        try:
            db.add(entry)
            db.commit()
            db.refresh(entry)

            save_agent_state(
                db,
                self.name,
                {
                    "last_waitlist_entry": entry.id,
                    "last_action": "JOIN"
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db, self.name, message.sender, "FAILURE",
                {"reason": "Could not join waitlist"},
                message.conversation_id
            )

        return send_message(
            db, self.name, message.sender, "INFORM",
            {
                "waitlist_id": entry.id,
                "status": "waiting",
                "event_id": event_id,
                "quantity": quantity,
                "message": "Successfully joined the waitlist"
            },
            message.conversation_id
        )

    # --------------------------------------------------
    # 2. OFFER AVAILABLE TICKETS
    # --------------------------------------------------

    def offer_available_tickets(self, db: Session, message):

        event_id = message.content.get("event_id")

        if (
            not isinstance(event_id, int)
            or isinstance(event_id, bool)
            or event_id <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid event ID"},
                message.conversation_id
            )

        event = db.query(Event).filter(
            Event.id == event_id,
            Event.status == "active"
        ).first()

        if not event:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Event not found or inactive"},
                message.conversation_id
            )

        now = datetime.utcnow()

        # Expire old offers before calculating availability
        expired_entries = db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.status == "offered",
            WaitlistEntry.hold_expires_at <= now
        ).all()

        for expired in expired_entries:
            expired.status = "expired"

        try:
            db.commit()
        except Exception:
            db.rollback()
            return send_message(
                db, self.name, message.sender, "FAILURE",
                {"reason": "Could not update expired offers"},
                message.conversation_id
            )

        # Count confirmed bookings
        bookings = db.query(Booking).filter(
            Booking.event_id == event_id,
            Booking.status == "confirmed"
        ).all()

        booked_count = sum(b.quantity for b in bookings)

        # Count tickets already held by other waitlist offers
        active_offers = db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.status == "offered",
            WaitlistEntry.hold_expires_at > now
        ).all()

        held_count = sum(entry.quantity for entry in active_offers)

        available = event.total_tickets - booked_count - held_count

        if available <= 0:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "No tickets currently available"},
                message.conversation_id
            )

        # Select the earliest waiting customer
        entry = db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.status == "waiting"
        ).order_by(
            WaitlistEntry.created_at.asc(),
            WaitlistEntry.id.asc()
        ).first()

        if not entry:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "No customers in the waitlist"},
                message.conversation_id
            )

        if entry.quantity > available:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {
                    "reason": "Available tickets are insufficient for the first waitlist entry",
                    "available_tickets": available,
                    "requested_tickets": entry.quantity
                },
                message.conversation_id
            )

        # Create temporary ticket hold
        entry.status = "offered"
        entry.hold_expires_at = (
            now + timedelta(minutes=self.hold_minutes)
        )

        try:
            db.commit()
            db.refresh(entry)

            save_agent_state(
                db,
                self.name,
                {
                    "last_offered_waitlist_id": entry.id,
                    "last_event_id": event_id,
                    "last_action": "OFFER"
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db, self.name, message.sender, "FAILURE",
                {"reason": "Could not create ticket hold"},
                message.conversation_id
            )

        offer_content = {
            "action": "WAITLIST_OFFER",
            "waitlist_id": entry.id,
            "user_id": entry.user_id,
            "event_id": event_id,
            "quantity": entry.quantity,
            "expires_at": entry.hold_expires_at.isoformat(),
            "hold_minutes": self.hold_minutes
        }

        # Notify NotificationAgent through JSON message
        send_message(
            db,
            self.name,
            "NotificationAgent",
            "INFORM",
            offer_content,
            message.conversation_id
        )

        # Inform the original requester
        return send_message(
            db,
            self.name,
            message.sender,
            "INFORM",
            {
                "waitlist_id": entry.id,
                "status": "offered",
                "user_id": entry.user_id,
                "quantity": entry.quantity,
                "expires_at": entry.hold_expires_at.isoformat(),
                "message": "Tickets temporarily offered to the next waitlist customer"
            },
            message.conversation_id
        )

    # --------------------------------------------------
    # 3. CONFIRM TICKET HOLD
    # --------------------------------------------------

    def confirm_hold(self, db: Session, message):

        waitlist_id = message.content.get("waitlist_id")
        requested_user_id = message.content.get("user_id")

        if (
            not isinstance(waitlist_id, int)
            or isinstance(waitlist_id, bool)
            or waitlist_id <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid waitlist ID"},
                message.conversation_id
            )

        entry = db.query(WaitlistEntry).filter(
            WaitlistEntry.id == waitlist_id,
            WaitlistEntry.status == "offered"
        ).first()

        if not entry:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "No active ticket offer found"},
                message.conversation_id
            )

        if (
            requested_user_id is not None
            and requested_user_id != entry.user_id
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Waitlist user mismatch"},
                message.conversation_id
            )

        if (
            entry.hold_expires_at is None
            or entry.hold_expires_at <= datetime.utcnow()
        ):
            entry.status = "expired"

            try:
                db.commit()
            except Exception:
                db.rollback()

            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Ticket offer has expired"},
                message.conversation_id
            )

        # Create booking for accepted waitlist offer
        payment_reference = (
            "SIM-" + uuid.uuid4().hex[:12].upper()
        )

        event = db.query(Event).filter(
            Event.id == entry.event_id,
            Event.status == "active"
        ).first()

        if not event:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Event is no longer active"},
                message.conversation_id
            )

        booking = Booking(
            user_id=entry.user_id,
            event_id=entry.event_id,
            quantity=entry.quantity,
            total_amount=event.ticket_price * entry.quantity,
            status="confirmed",
            payment_reference=payment_reference
        )

        try:
            db.add(booking)
            entry.status = "accepted"

            db.commit()
            db.refresh(booking)

            save_agent_state(
                db,
                self.name,
                {
                    "last_accepted_waitlist_id": entry.id,
                    "last_booking_id": booking.id,
                    "last_action": "CONFIRM"
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db, self.name, message.sender, "FAILURE",
                {"reason": "Could not confirm waitlist booking"},
                message.conversation_id
            )

        # Request TicketAgent to generate tickets
        send_message(
            db,
            self.name,
            "TicketAgent",
            "REQUEST",
            {
                "booking_id": booking.id,
                "user_id": entry.user_id,
                "event_id": entry.event_id,
                "quantity": entry.quantity
            },
            message.conversation_id
        )

        # Notify NotificationAgent
        send_message(
            db,
            self.name,
            "NotificationAgent",
            "INFORM",
            {
                "action": "WAITLIST_CONFIRMED",
                "waitlist_id": entry.id,
                "booking_id": booking.id,
                "user_id": entry.user_id,
                "event_id": entry.event_id
            },
            message.conversation_id
        )

        return send_message(
            db, self.name, message.sender, "INFORM",
            {
                "waitlist_id": entry.id,
                "booking_id": booking.id,
                "status": "accepted",
                "payment_reference": payment_reference,
                "message": "Waitlist offer accepted and booking confirmed"
            },
            message.conversation_id
        )

    # --------------------------------------------------
    # 4. AUTOMATICALLY EXPIRE HOLDS
    # --------------------------------------------------

    def expire_holds(self, db: Session):

        now = datetime.utcnow()

        expired_entries = db.query(WaitlistEntry).filter(
            WaitlistEntry.status == "offered",
            WaitlistEntry.hold_expires_at <= now
        ).all()

        affected_events = set()

        for entry in expired_entries:
            entry.status = "expired"
            affected_events.add(entry.event_id)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        return list(affected_events)
