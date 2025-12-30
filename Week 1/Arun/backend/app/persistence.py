# backend/app/persistence.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict

from .pinecone_client import index
from .models import UserProfile, StoredAppointment


# -------------------------------
# Pinecone metadata safety helper
# -------------------------------

def _clean_metadata(md: Dict) -> Dict:
    """
    Pinecone does not allow null values.
    Remove keys where value is None or empty.
    """
    return {
        k: v
        for k, v in md.items()
        if v is not None and v != []
    }


IST = timezone(timedelta(hours=5, minutes=30))

# Keep this consistent with your index dimension
DUMMY_VECTOR_DIM = 64

DUMMY_VECTOR = [0.0] * DUMMY_VECTOR_DIM
DUMMY_VECTOR[0] = 1.0


# -------------------------------------------------
#  USER PROFILE + PREFERENCES
# -------------------------------------------------

def save_user(user: UserProfile, preferences: Optional[Dict] = None) -> None:
    """
    Store or update user profile + preferences in Pinecone under namespace 'users'.

    Preferences must already be validated and optional.
    """
    metadata = {
        "type": "user",
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
    }

    if preferences:
        metadata.update(preferences)

    cleaned = _clean_metadata(metadata)

    index.upsert(
        vectors=[
            (
                f"user-{user.user_id}",
                DUMMY_VECTOR,
                cleaned,
            )
        ],
        namespace="users",
    )


# -------------------------------------------------
#  APPOINTMENTS
# -------------------------------------------------

def save_stored_appointment(appt: StoredAppointment) -> None:
    """
    Store StoredAppointment in Pinecone under namespace 'appointments'.
    """
    if not appt.id:
        raise ValueError("StoredAppointment.id must be set before saving")

    metadata = _clean_metadata({
        "type": "appointment",
        "id": appt.id,
        "user_id": appt.user_id,
        "patient_name": appt.patient_name,
        "reason": appt.reason,
        "start_time": appt.start_time.isoformat(),
        "end_time": appt.end_time.isoformat(),
        "google_event_id": appt.google_event_id,
        "status": appt.status,
    })

    index.upsert(
        vectors=[
            (
                f"appt-{appt.id}",
                DUMMY_VECTOR,
                metadata,
            )
        ],
        namespace="appointments",
    )


def _stored_appointment_from_metadata(md: dict) -> StoredAppointment:
    return StoredAppointment(
        id=md["id"],
        user_id=md["user_id"],
        patient_name=md.get("patient_name", ""),
        reason=md.get("reason", ""),
        start_time=datetime.fromisoformat(md["start_time"]),
        end_time=datetime.fromisoformat(md["end_time"]),
        google_event_id=md.get("google_event_id"),
        status=md.get("status", "confirmed"),
    )


def get_appointments_for_user(
    user_id: str,
    limit: int = 50
) -> List[StoredAppointment]:
    result = index.query(
        namespace="appointments",
        vector=DUMMY_VECTOR,
        top_k=limit,
        filter={"user_id": {"$eq": user_id}},
        include_values=False,
        include_metadata=True,
    )

    matches = result.get("matches") or []

    appointments: List[StoredAppointment] = []
    for match in matches:
        md = match.get("metadata") or {}
        if md.get("type") != "appointment":
            continue
        appointments.append(_stored_appointment_from_metadata(md))

    appointments.sort(key=lambda a: a.start_time)
    return appointments


def get_latest_confirmed_future_appointment(
    user_id: str,
    limit: int = 50
) -> Optional[StoredAppointment]:
    appointments = get_appointments_for_user(user_id, limit=limit)

    now = datetime.now(IST)
    future = [
        a for a in appointments
        if a.status == "confirmed" and a.start_time >= now
    ]

    future.sort(key=lambda a: a.start_time)
    return future[0] if future else None
