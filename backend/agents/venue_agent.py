
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.models import Venue, Event, VenueHireRequest
from backend.agents.message_bus import (
    send_message,
    save_agent_state
)


class VenueAgent:

    def __init__(self):
        self.name = "VenueAgent"
        self.goal = "Manage venue availability, capacity and private hire requests"

        # Simple configurable quotation rule
        self.base_hire_price = 10000
        self.price_per_attendee = 100

    def handle_message(self, db: Session, message):

        content = message.content
        action = content.get("action", "CHECK_AVAILABILITY")

        if action == "HIRE_REQUEST":
            return self.process_hire_request(db, message)

        return self.check_availability(db, message)

    # --------------------------------------------------
    # 1. CONVERT DATE AND TIME
    # --------------------------------------------------

    def parse_datetime(self, value):

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            return datetime.fromisoformat(value)

        raise ValueError("Invalid date/time format")

    # --------------------------------------------------
    # 2. CHECK VENUE AVAILABILITY
    # --------------------------------------------------

    def check_availability(self, db: Session, message):

        content = message.content

        venue_id = content.get("venue_id")
        start_value = content.get("start_at")
        end_value = content.get("end_at")
        required_capacity = content.get("required_capacity", 0)

        if (
            not isinstance(venue_id, int)
            or isinstance(venue_id, bool)
            or venue_id <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid venue ID"},
                message.conversation_id
            )

        if (
            not isinstance(required_capacity, int)
            or isinstance(required_capacity, bool)
            or required_capacity <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid required capacity"},
                message.conversation_id
            )

        try:
            start_at = self.parse_datetime(start_value)
            end_at = self.parse_datetime(end_value)

        except (ValueError, TypeError):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid date/time format. Use ISO format."},
                message.conversation_id
            )

        if start_at >= end_at:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Start time must be before end time"},
                message.conversation_id
            )

        venue = db.query(Venue).filter(
            Venue.id == venue_id,
            Venue.is_active.is_(True)
        ).first()

        if not venue:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Venue not found or inactive"},
                message.conversation_id
            )

        if required_capacity > venue.capacity:
            return self.propose_alternatives(
                db, message, start_at, end_at,
                required_capacity,
                "Required capacity exceeds venue capacity"
            )

        if self.has_conflict(
            db, venue, start_at, end_at
        ):
            return self.propose_alternatives(
                db, message, start_at, end_at,
                required_capacity,
                "Venue is not available during this time"
            )

        save_agent_state(
            db,
            self.name,
            {
                "last_checked_venue": venue.id,
                "last_decision": "available",
                "last_start_at": start_at.isoformat(),
                "last_end_at": end_at.isoformat()
            }
        )

        return send_message(
            db,
            self.name,
            message.sender,
            "AGREE",
            {
                "reason": "Venue is available",
                "venue_id": venue.id,
                "venue_name": venue.name,
                "capacity": venue.capacity
            },
            message.conversation_id
        )

    # --------------------------------------------------
    # 3. CHECK CONFLICTS INCLUDING TURNAROUND TIME
    # --------------------------------------------------

    def has_conflict(self, db, venue, start_at, end_at):

        buffer = timedelta(
            minutes=venue.turnaround_minutes
        )

        conflicting_events = db.query(Event).filter(
            Event.venue_id == venue.id,
            Event.status == "active",
            Event.start_at < end_at + buffer,
            Event.end_at > start_at - buffer
        ).first()

        return conflicting_events is not None

    # --------------------------------------------------
    # 4. PROPOSE ALTERNATIVE VENUES
    # --------------------------------------------------

    def propose_alternatives(
        self,
        db,
        message,
        start_at,
        end_at,
        required_capacity,
        reason
    ):

        venues = db.query(Venue).filter(
            Venue.is_active.is_(True),
            Venue.capacity >= required_capacity
        ).all()

        alternatives = []

        for venue in venues:

            if self.has_conflict(
                db, venue, start_at, end_at
            ):
                continue

            alternatives.append({
                "venue_id": venue.id,
                "venue_name": venue.name,
                "location": venue.location,
                "capacity": venue.capacity
            })

        if alternatives:

            return send_message(
                db,
                self.name,
                message.sender,
                "PROPOSE",
                {
                    "reason": reason,
                    "alternatives": alternatives,
                    "message": "Alternative available venues are proposed"
                },
                message.conversation_id
            )

        return send_message(
            db,
            self.name,
            message.sender,
            "REFUSE",
            {
                "reason": reason,
                "message": "No suitable alternative venues are available"
            },
            message.conversation_id
        )

    # --------------------------------------------------
    # 5. PRIVATE VENUE HIRE REQUEST
    # --------------------------------------------------

    def process_hire_request(self, db: Session, message):

        content = message.content

        user_id = content.get("user_id")
        venue_id = content.get("venue_id")
        start_value = content.get("start_at")
        end_value = content.get("end_at")
        expected_attendees = content.get(
            "expected_attendees", 0
        )
        purpose = content.get("purpose", "")

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
            not isinstance(expected_attendees, int)
            or isinstance(expected_attendees, bool)
            or expected_attendees <= 0
        ):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid attendee count"},
                message.conversation_id
            )

        try:
            start_at = self.parse_datetime(start_value)
            end_at = self.parse_datetime(end_value)

        except (ValueError, TypeError):
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Invalid date/time format"},
                message.conversation_id
            )

        if start_at >= end_at:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Start time must be before end time"},
                message.conversation_id
            )

        venue = db.query(Venue).filter(
            Venue.id == venue_id,
            Venue.is_active.is_(True)
        ).first()

        if not venue:
            return send_message(
                db, self.name, message.sender, "REFUSE",
                {"reason": "Venue not found or inactive"},
                message.conversation_id
            )

        # Calculate automatic quotation
        quoted_price = (
            self.base_hire_price
            + expected_attendees * self.price_per_attendee
        )

        # Check availability and capacity
        if (
            expected_attendees > venue.capacity
            or self.has_conflict(
                db, venue, start_at, end_at
            )
        ):

            request = VenueHireRequest(
                user_id=user_id,
                venue_id=venue.id,
                start_at=start_at,
                end_at=end_at,
                expected_attendees=expected_attendees,
                purpose=purpose,
                quoted_price=quoted_price,
                status="rejected",
                decision_reason="Venue unavailable or capacity exceeded"
            )

            try:
                db.add(request)
                db.commit()
                db.refresh(request)

            except Exception:
                db.rollback()

                return send_message(
                    db, self.name, message.sender, "FAILURE",
                    {"reason": "Could not save venue hire request"},
                    message.conversation_id
                )

            return self.propose_alternatives(
                db,
                message,
                start_at,
                end_at,
                expected_attendees,
                "Requested venue is unavailable or too small"
            )

        # Automatically approve available venue hire
        request = VenueHireRequest(
            user_id=user_id,
            venue_id=venue.id,
            start_at=start_at,
            end_at=end_at,
            expected_attendees=expected_attendees,
            purpose=purpose,
            quoted_price=quoted_price,
            status="approved",
            decision_reason="Automatically approved: venue available and capacity sufficient"
        )

        try:
            db.add(request)
            db.commit()
            db.refresh(request)

            save_agent_state(
                db,
                self.name,
                {
                    "last_hire_request_id": request.id,
                    "last_hire_status": "approved",
                    "last_quoted_price": quoted_price
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db, self.name, message.sender, "FAILURE",
                {"reason": "Could not save venue hire request"},
                message.conversation_id
            )

        return send_message(
            db,
            self.name,
            message.sender,
            "AGREE",
            {
                "hire_request_id": request.id,
                "venue_id": venue.id,
                "venue_name": venue.name,
                "status": "approved",
                "quoted_price": quoted_price,
                "currency": "LKR",
                "message": "Private venue hire request approved automatically"
            },
            message.conversation_id
        )
