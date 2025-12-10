# backend/main.py

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from app.rate_limit import rate_limiter
import asyncio
import uuid
from app.llm.agent import reset_violation_state


# Week 1 agent and tools
from app.llm.agent import (
    agent,
    Appointment as BookingAppointment,  # <-- Week 1 Appointment (name, date, time, etc.)
    dental_booking_agent,
    check_appointment_slot_available,
    appointmentDetails,
)

# Week 3 models + infra
from app.models import StoredAppointment
from app.persistence import save_stored_appointment, get_appointments_for_user
from app.google_calendar import is_slot_free, create_calendar_event
from app.rate_limit import rate_limiter


app = FastAPI()

# Allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str  # ONLY the current user message


# Global chat history for Week 1 agent
msg_history: List[Any] = []


@app.post("/chat", dependencies=[Depends(rate_limiter)])
def chat(req: ChatRequest):
    """
    Simple, synchronous chat endpoint.

    - Appends user message to msg_history
    - Calls agent.run_sync() directly (same as test_agent.py)
    - Updates msg_history
    - Returns either {"reply": "..."} or {"error": "..."}
    """
    global msg_history
    try:
        msg_history.append({"role": "user", "content": req.message})

        result = agent.run_sync(
            req.message,
            message_history=msg_history,
        )

        msg_history = result.all_messages()

        return {"reply": result.output}
    except Exception as e:
        return {"error": str(e)}



# ---------- Week 1 booking endpoints stay as-is ----------

class BookingRequest(BaseModel):
    name: str
    preferred_date: str  # DD-MM-YYYY
    time: str
    reason: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


@app.post("/book", dependencies=[Depends(rate_limiter)])
async def book(b: BookingRequest):
    """Directly call the Week 1 dental_booking_agent tool with validated booking data."""
    try:
        appointment = BookingAppointment(
            name=b.name,
            preferred_date=b.preferred_date,
            time=b.time,
            reason=b.reason,
            contact_email=b.contact_email,
            contact_phone=b.contact_phone,
        )
    except Exception as e:
        return {"success": False, "error": f"Validation error: {e}"}

    try:
        result = dental_booking_agent(None, appointment)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/check_slot", dependencies=[Depends(rate_limiter)])
async def check_slot(b: BookingRequest):
    """Check availability for the requested time slot using the Week 1 agent's plain tool."""
    try:
        appointment = BookingAppointment(
            name=b.name or "",
            preferred_date=b.preferred_date,
            time=b.time,
            reason=b.reason or "",
            contact_email=b.contact_email,
            contact_phone=b.contact_phone,
        )
    except Exception as e:
        return {"success": False, "error": f"Validation error: {e}"}

    try:
        status_text = check_appointment_slot_available(appointment)
        return {"success": True, "status": status_text}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/appointment")
async def get_latest_appointment():
    """
    Return the last booked appointment details (in-memory).
    This is Week 1 behavior, kept for demo/testing.
    """
    return {"appointmentDetails": appointmentDetails}


@app.post("/reset")
async def reset_chat():
    global msg_history, appointmentDetails
    msg_history = []
    try:
        appointmentDetails.clear()
    except Exception:
        appointmentDetails = {}

    # Reset moderation violations for a fresh conversation
    reset_violation_state()

    return {"status": "ok"}



# ---------- Week 3: Google Calendar + Pinecone appointments ----------

@app.post(
    "/appointments",
    response_model=StoredAppointment,
    dependencies=[Depends(rate_limiter)],
)
async def create_appointment(appt: StoredAppointment):
    """
    Week 3 endpoint:
      1. Check Google Calendar availability.
      2. If free, create event in Google Calendar.
      3. Save appointment in Pinecone as StoredAppointment.
    """
    # Generate ID if not provided
    if not appt.id:
        appt.id = str(uuid.uuid4())

    # Check slot against Google Calendar
    if not is_slot_free(appt.start_time, appt.end_time):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requested time slot is not available. Please choose another time.",
        )

    # Create calendar event
    event_id = create_calendar_event(appt)
    appt.google_event_id = event_id
    appt.status = "confirmed"

    # Save in Pinecone
    save_stored_appointment(appt)

    return appt


@app.get(
    "/appointments",
    response_model=List[StoredAppointment],
    dependencies=[Depends(rate_limiter)],
)
async def list_appointments(user_id: str, limit: int = 50):
    """
    Week 3 endpoint:
      List appointments for a given user_id using Pinecone metadata filter.
    """
    return get_appointments_for_user(user_id=user_id, limit=limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
