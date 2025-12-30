# backend/app/models.py

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional


class UserPreferences(BaseModel):
    """
    Long-term personalization stored for a user.
    Updated silently whenever user states a preference —
    before or after booking.
    """
    preferred_times: List[str] = Field(default_factory=list)
    preferred_dentist: Optional[str] = None
    insurance_provider: Optional[str] = None
    dental_anxiety: Optional[bool] = None
    prefers_brief_responses: Optional[bool] = None
    prefers_emojis: Optional[bool] = None
    tone: Optional[str] = None  # 'formal' | 'friendly'

    # Helps enforce memory update logic
    last_updated: Optional[str] = Field(default_factory=lambda: datetime.utcnow().isoformat())


class UserProfile(BaseModel):
    """
    Persistent user profile stored in Pinecone.
    """
    user_id: str                      # typically email
    name: str
    email: EmailStr
    phone: Optional[str] = None

    # 🚀 New: stored preferences associated with user identity
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class StoredAppointment(BaseModel):
    """
    Persistent appointment including calendar event metadata.
    """
    id: Optional[str] = None          # UUID, generated server-side
    user_id: str                      # link to UserProfile.user_id (email)
    patient_name: str
    reason: str

    start_time: datetime              # ISO datetime
    end_time: datetime
    google_event_id: Optional[str] = None

    # "confirmed" | "cancelled" | (future: "pending")
    status: str = "confirmed"
