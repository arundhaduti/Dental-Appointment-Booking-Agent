# backend/app/persistence.py

from __future__ import annotations

from datetime import datetime
from typing import List

from .pinecone_client import index  # assumes you already have this
from .models import UserProfile, StoredAppointment

# Keep this consistent with your index dimension
DUMMY_VECTOR_DIM = 64

# Pinecone requires at least one non-zero value in dense vectors.
# We don't care about actual similarity here (we use metadata filters),
# so we just make the first dimension 1.0 and the rest 0.0.
DUMMY_VECTOR = [0.0] * DUMMY_VECTOR_DIM
DUMMY_VECTOR[0] = 1.0



def save_user(user: UserProfile) -> None:
    """
    Store user profile in Pinecone under namespace 'users'.
    """
    index.upsert(
        vectors=[
            (
                f"user-{user.user_id}",
                DUMMY_VECTOR,
                {
                    "type": "user",
                    "user_id": user.user_id,
                    "name": user.name,
                    "email": user.email,
                    "phone": user.phone or "",
                },
            )
        ],
        namespace="users",
    )


def save_stored_appointment(appt: StoredAppointment) -> None:
    """
    Store StoredAppointment in Pinecone under namespace 'appointments'.
    All structured data goes into metadata.
    """
    if not appt.id:
        raise ValueError("StoredAppointment.id must be set before saving")

    index.upsert(
        vectors=[
            (
                f"appt-{appt.id}",
                DUMMY_VECTOR,
                {
                    "type": "appointment",
                    "id": appt.id,
                    "user_id": appt.user_id,
                    "patient_name": appt.patient_name,
                    "reason": appt.reason,
                    "start_time": appt.start_time.isoformat(),
                    "end_time": appt.end_time.isoformat(),
                    "google_event_id": appt.google_event_id or "",
                    "status": appt.status,
                },
            )
        ],
        namespace="appointments",
    )


def _stored_appointment_from_metadata(md: dict) -> StoredAppointment:
    """
    Helper: convert Pinecone metadata back into a StoredAppointment model.
    """
    return StoredAppointment(
        id=md["id"],
        user_id=md["user_id"],
        patient_name=md.get("patient_name", ""),
        reason=md.get("reason", ""),
        start_time=datetime.fromisoformat(md["start_time"]),
        end_time=datetime.fromisoformat(md["end_time"]),
        google_event_id=md.get("google_event_id") or None,
        status=md.get("status", "confirmed"),
    )


def get_appointments_for_user(user_id: str, limit: int = 50) -> List[StoredAppointment]:
    """
    Option C: Use Pinecone metadata filtering + namespace search.

    We query the 'appointments' namespace with:
      - a dummy vector (because Pinecone requires a vector)
      - a metadata filter on user_id
      - include_metadata=True so we can reconstruct StoredAppointment models

    'limit' is the max number of appointments to return for this user.
    """
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

    # Sort by start time ascending before returning
    appointments.sort(key=lambda a: a.start_time)

    return appointments
