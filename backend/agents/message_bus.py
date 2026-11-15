
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models import AgentMessage, AgentState


# Message structure used by all agents
class AgentMessageSchema(BaseModel):
    sender: str
    receiver: str
    performative: Literal[
        "REQUEST",
        "AGREE",
        "REFUSE",
        "PROPOSE",
        "INFORM",
        "FAILURE"
    ]
    content: dict = Field(default_factory=dict)
    conversation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )


# Send a JSON message from one agent to another
def send_message(
    db: Session,
    sender: str,
    receiver: str,
    performative: str,
    content: dict,
    conversation_id: str | None = None
):
    message_data = AgentMessageSchema(
        sender=sender,
        receiver=receiver,
        performative=performative,
        content=content,
        conversation_id=conversation_id or str(uuid.uuid4())
    )

    new_message = AgentMessage(
        sender=message_data.sender,
        receiver=message_data.receiver,
        performative=message_data.performative,
        content=message_data.content,
        conversation_id=message_data.conversation_id
    )

    try:
        db.add(new_message)
        db.commit()
        db.refresh(new_message)
        return new_message
    except Exception:
        db.rollback()
        raise


# Retrieve messages addressed to a particular agent
def get_agent_messages(
    db: Session,
    agent_name: str,
    after_id: int = 0
):
    messages = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.receiver == agent_name,
            AgentMessage.id > after_id
        )
        .order_by(AgentMessage.id.asc())
        .all()
    )

    return messages


# Save or update an agent's persistent state
def save_agent_state(
    db: Session,
    agent_name: str,
    state: dict
):
    agent_state = (
        db.query(AgentState)
        .filter(AgentState.agent_name == agent_name)
        .first()
    )

    if agent_state:
        agent_state.state = state
        agent_state.updated_at = datetime.utcnow()
    else:
        agent_state = AgentState(
            agent_name=agent_name,
            state=state
        )
        db.add(agent_state)

    try:
        db.commit()
        db.refresh(agent_state)
        return agent_state
    except Exception:
        db.rollback()
        raise


# Retrieve an agent's saved state
def get_agent_state(db: Session, agent_name: str):
    return (
        db.query(AgentState)
        .filter(AgentState.agent_name == agent_name)
        .first()
    )
