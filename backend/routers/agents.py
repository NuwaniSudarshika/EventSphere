
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AgentMessage
from backend.agents.message_bus import send_message


router = APIRouter(prefix="/agents", tags=["Multi-Agent System"])


class AgentRequest(BaseModel):
    receiver: str
    content: dict = Field(default_factory=dict)
    conversation_id: str | None = None


@router.post("/message")
def send_agent_request(
    request: AgentRequest,
    db: Session = Depends(get_db)
):
    allowed_agents = [
        "VenueAgent",
        "BookingAgent",
        "TicketAgent",
        "WaitlistAgent",
        "NotificationAgent"
    ]

    if request.receiver not in allowed_agents:
        raise HTTPException(
            status_code=400,
            detail="Unknown agent"
        )

    message = send_message(
        db=db,
        sender="API",
        receiver=request.receiver,
        performative="REQUEST",
        content=request.content,
        conversation_id=request.conversation_id
    )

    return {
        "message": "Agent request submitted",
        "message_id": message.id,
        "conversation_id": message.conversation_id,
        "receiver": message.receiver
    }


@router.get("/messages/{conversation_id}")
def get_conversation_messages(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    messages = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.conversation_id == conversation_id
        )
        .order_by(AgentMessage.id.asc())
        .all()
    )

    return [
        {
            "id": msg.id,
            "sender": msg.sender,
            "receiver": msg.receiver,
            "performative": msg.performative,
            "content": msg.content,
            "conversation_id": msg.conversation_id
        }
        for msg in messages
    ]
