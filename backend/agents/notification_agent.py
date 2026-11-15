
from datetime import datetime

from sqlalchemy.orm import Session

from backend.agents.message_bus import (
    send_message,
    save_agent_state,
    get_agent_state
)


class NotificationAgent:

    def __init__(self):
        self.name = "NotificationAgent"
        self.goal = "Notify users about event and booking updates"

        self.notification_messages = {
            "BOOKING_CONFIRMED":
                "Your event booking has been confirmed.",

            "TICKET_GENERATED":
                "Your event tickets are ready.",

            "WAITLIST_OFFER":
                "Tickets are available. Please confirm before the offer expires.",

            "WAITLIST_CONFIRMED":
                "Your waitlist offer has been accepted and your booking is confirmed.",

            "WAITLIST_EXPIRED":
                "Your ticket offer has expired.",

            "VENUE_APPROVED":
                "Your venue request has been approved.",

            "VENUE_REJECTED":
                "Your venue request has been rejected."
        }

    def handle_message(self, db: Session, message):

        content = message.content or {}

        action = content.get("action", "GENERAL")

        # 1. Get notification text
        notification_text = self.notification_messages.get(
            action,
            content.get(
                "message",
                "You have a new notification."
            )
        )

        # 2. Prepare notification information
        notification_data = {
            "user_id": content.get("user_id"),
            "action": action,
            "message": notification_text,
            "details": content,
            "sender": message.sender,
            "conversation_id": message.conversation_id,
            "created_at": datetime.utcnow().isoformat()
        }

        try:
            # 3. Get existing notification history
            existing_state = get_agent_state(
                db,
                self.name
            )

            if existing_state and existing_state.state:
                notification_history = existing_state.state.get(
                    "notification_history", []
                )
            else:
                notification_history = []

            # 4. Add new notification
            notification_history.append(notification_data)

            # Keep latest 100 notifications
            notification_history = notification_history[-100:]

            # 5. Save notification history
            save_agent_state(
                db,
                self.name,
                {
                    "last_notification": notification_data,
                    "notification_history": notification_history,
                    "total_notifications": len(notification_history),
                    "last_sender": message.sender
                }
            )

        except Exception:
            db.rollback()

            return send_message(
                db,
                self.name,
                message.sender,
                "FAILURE",
                {
                    "reason": "Could not save notification"
                },
                message.conversation_id
            )

        # 6. Inform the sender
        return send_message(
            db,
            self.name,
            message.sender,
            "INFORM",
            {
                "status": "notification_processed",
                "action": action,
                "notification": notification_data
            },
            message.conversation_id
        )
