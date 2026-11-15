
import asyncio
import uuid

from backend.database import SessionLocal
from backend.models import AgentMessage

from backend.agents.message_bus import (
    get_agent_state,
    save_agent_state,
    send_message
)

from backend.agents.venue_agent import VenueAgent
from backend.agents.booking_agent import BookingAgent
from backend.agents.ticket_agent import TicketAgent
from backend.agents.waitlist_agent import WaitlistAgent
from backend.agents.notification_agent import NotificationAgent


# Register all five agents
AGENTS = {
    "VenueAgent": VenueAgent(),
    "BookingAgent": BookingAgent(),
    "TicketAgent": TicketAgent(),
    "WaitlistAgent": WaitlistAgent(),
    "NotificationAgent": NotificationAgent()
}


def process_pending_messages(db):

    # Get the last processed message ID
    cursor = get_agent_state(db, "MessageDispatcher")

    last_id = 0

    if cursor and cursor.state:
        last_id = cursor.state.get("last_processed_id", 0)

    # Get pending messages in order
    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.id > last_id)
        .order_by(AgentMessage.id.asc())
        .all()
    )

    processed_count = 0

    for message in messages:

        agent = AGENTS.get(message.receiver)

        # REQUEST messages go to the relevant agent.
        # NotificationAgent also receives INFORM messages.
        should_dispatch = (
            message.performative == "REQUEST"
            or (
                message.performative == "INFORM"
                and message.receiver == "NotificationAgent"
            )
        )

        try:

            if agent and should_dispatch:
                agent.handle_message(db, message)
                processed_count += 1

            # Update dispatcher cursor after successful processing
            save_agent_state(
                db,
                "MessageDispatcher",
                {
                    "last_processed_id": message.id
                }
            )

        except Exception:
            db.rollback()
            raise

    return processed_count


async def run_message_listener(stop_event, interval=2):

    print("EventSphere Agent Listener Started")

    while not stop_event.is_set():

        db = SessionLocal()

        try:
            processed = process_pending_messages(db)

            if processed > 0:
                print(
                    f"Agent Dispatcher: {processed} message(s) processed"
                )

        except Exception as error:
            db.rollback()
            print("Agent Listener Error:", error)

        finally:
            db.close()

        await asyncio.sleep(interval)

    print("EventSphere Agent Listener Stopped")


async def run_waitlist_timer(stop_event, interval=30):

    print("EventSphere Waitlist Timer Started")

    while not stop_event.is_set():

        db = SessionLocal()

        try:

            waitlist_agent = AGENTS["WaitlistAgent"]

            # Find expired offers
            expired_event_ids = waitlist_agent.expire_holds(db)

            # Send JSON REQUEST messages through the message bus
            for event_id in expired_event_ids:

                send_message(
                    db=db,
                    sender="WaitlistTimer",
                    receiver="WaitlistAgent",
                    performative="REQUEST",
                    content={
                        "action": "RELEASE",
                        "event_id": event_id
                    },
                    conversation_id=str(uuid.uuid4())
                )

                print(
                    f"Waitlist Timer: Release request sent for event {event_id}"
                )

        except Exception as error:
            db.rollback()
            print("Waitlist Timer Error:", error)

        finally:
            db.close()

        await asyncio.sleep(interval)

    print("EventSphere Waitlist Timer Stopped")
