
from pydantic import BaseModel, EmailStr, Field


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
