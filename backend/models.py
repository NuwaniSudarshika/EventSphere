
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, JSON, CheckConstraint
)
from datetime import datetime

from backend.database import Base


# 1. Users Table
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="attendee", nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# 2. Venues Table
class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    location = Column(String(200), nullable=False)
    capacity = Column(Integer, nullable=False)
    turnaround_minutes = Column(Integer, default=60)
    description = Column(Text)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("capacity > 0"),
    )


# 3. Events Table
class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    ticket_price = Column(Integer, default=0)
    total_tickets = Column(Integer, nullable=False)
    status = Column(String(30), default="active")
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("total_tickets > 0"),
        CheckConstraint("ticket_price >= 0"),
    )


# 4. Bookings Table
class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_amount = Column(Integer, nullable=False)
    status = Column(String(30), default="confirmed")
    payment_reference = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("quantity > 0"),
    )


# 5. Tickets Table
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    ticket_code = Column(String(100), unique=True, nullable=False)
    qr_token = Column(String(255), unique=True, nullable=False)
    status = Column(String(30), default="valid")
    checked_in_at = Column(DateTime)
    checked_in_by = Column(Integer, ForeignKey("users.id"))


# 6. Waitlist Table
class WaitlistEntry(Base):
    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(30), default="waiting")
    hold_expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


# 7. Venue Hire Requests Table
class VenueHireRequest(Base):
    __tablename__ = "venue_hire_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    expected_attendees = Column(Integer, nullable=False)
    purpose = Column(Text)
    quoted_price = Column(Integer)
    status = Column(String(30), default="pending")
    decision_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# 8. Agent Messages Table
class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String(50), nullable=False)
    receiver = Column(String(50), nullable=False)
    performative = Column(String(20), nullable=False)
    content = Column(JSON, nullable=False)
    conversation_id = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Agent State Table
class AgentState(Base):
    __tablename__ = "agent_states"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(50), unique=True, nullable=False)
    state = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
