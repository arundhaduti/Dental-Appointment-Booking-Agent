# backend/app/models.py

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional


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


class UserMemory(BaseModel):
    """
    Long-term, SAFE user memory.

    Stored ONLY when the user explicitly states a preference or personal detail.
    NEVER inferred.
    """

    user_id: str = Field(..., description="User email (primary key)")

    # Basic identity (explicit only)
    name: Optional[str] = None
    phone: Optional[str] = None

    # Preferences (explicit statements only)
    preferred_times: List[str] = []
    preferred_dentist: Optional[str] = None
    insurance_provider: Optional[str] = None

    # Comfort & communication preferences
    dental_anxiety: Optional[bool] = None
    prefers_brief_responses: Optional[bool] = None
    prefers_emojis: Optional[bool] = None
    tone: Optional[str] = None  # 'formal' | 'friendly'

    # Metadata
    last_updated: datetime