# backend/app/models.py

from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserProfile(BaseModel):
    """
    Persistent user profile stored in Pinecone.
    user_id: typically an email or UUID
    """
    user_id: str
    name: str
    email: EmailStr
    phone: str | None = None


class StoredAppointment(BaseModel):
    """
    Week 3 appointment model for persistence + Google Calendar.

    This is intentionally separate from the Week 1 Appointment model
    in backend.app.llm.agent to avoid conflicts.
    """
    id: str | None = None              # UUID, generated server-side
    user_id: str                       # link to UserProfile.user_id (e.g. email)
    patient_name: str                  # human-readable name
    reason: str                        # cleaning, checkup, etc.

    start_time: datetime               # ISO datetime from frontend
    end_time: datetime

    google_event_id: str | None = None
    status: str = "confirmed"          # or "pending", "cancelled"
