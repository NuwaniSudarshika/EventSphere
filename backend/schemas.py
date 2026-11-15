
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


# User Registration Schema
class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


# User Response Schema
class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool

    class Config:
        from_attributes = True


# Login Response Schema
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# User Login Schema
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Venue Schemas

class VenueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    location: str = Field(min_length=2, max_length=200)
    capacity: int = Field(gt=0)
    turnaround_minutes: int = Field(default=60, ge=0)
    description: str | None = None


class VenueResponse(BaseModel):
    id: int
    name: str
    location: str
    capacity: int
    turnaround_minutes: int
    description: str | None
    is_active: bool

    class Config:
        from_attributes = True


# Event Schemas

class EventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    category: str | None = None
    venue_id: int = Field(gt=0)
    start_at: datetime
    end_at: datetime
    ticket_price: int = Field(default=0, ge=0)
    total_tickets: int = Field(gt=0)


class EventResponse(BaseModel):
    id: int
    title: str
    description: str | None
    category: str | None
    venue_id: int
    start_at: datetime
    end_at: datetime
    ticket_price: int
    total_tickets: int
    status: str

    class Config:
        from_attributes = True



# Booking Schemas

class BookingCreate(BaseModel):
    event_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class BookingResponse(BaseModel):
    id: int
    user_id: int
    event_id: int
    quantity: int
    total_amount: int
    status: str
    payment_reference: str | None
    created_at: datetime

    class Config:
        from_attributes = True


# Ticket Schemas

class TicketResponse(BaseModel):
    id: int
    booking_id: int
    ticket_code: str
    qr_token: str
    status: str

    class Config:
        from_attributes = True


class CheckInRequest(BaseModel):
    ticket_code: str


