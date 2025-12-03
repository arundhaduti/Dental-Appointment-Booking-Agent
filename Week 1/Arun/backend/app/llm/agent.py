from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple

from dateutil import parser
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, EmailStr
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.models import StoredAppointment, UserProfile
from app.persistence import (
    save_stored_appointment,
    save_user,
    get_latest_confirmed_future_appointment,
)
from app.google_calendar import (
    is_slot_free,
    create_calendar_event,
    update_calendar_event,
)

# ---------------------------------------------------------
#  Timezone setup
# ---------------------------------------------------------

try:
    from zoneinfo import ZoneInfo
    KOLKATA = ZoneInfo("Asia/Kolkata")
except Exception:
    KOLKATA = timezone(timedelta(hours=5, minutes=30))


def _normalize_input(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s)
    s = s.replace(",", "")
    return s


# ---------------------------------------------------------
#  Models
# ---------------------------------------------------------

class Appointment(BaseModel):
    """
    Booking schema used by the LLM and FastAPI.
    """
    name: str = Field(..., description="Patient's full name")
    preferred_date: str = Field(..., description="Appointment date in DD-MM-YYYY format or natural language")
    time: str = Field(..., description="Appointment time, flexible format")
    reason: str = Field(..., description="Reason for visit, e.g., Cleaning, Check-up, etc.")
    contact_email: EmailStr = Field(..., description="Email address used for booking")
    contact_phone: str = Field(..., description="10 digit phone number")

    @field_validator("preferred_date")
    @classmethod
    def validate_preferred_date(cls, v: str) -> str:
        now = datetime.now()
        s = _normalize_input(v)
        try:
            dt = parser.parse(s, dayfirst=True, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse date '{v}': {e}")

        candidate = dt.replace(year=now.year)
        if candidate.date() <= now.date():
            candidate = candidate.replace(year=now.year + 1)
        dt = candidate
        return dt.strftime("%d-%m-%Y")

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        """
        Accepts flexible time formats:
          - '9 AM', '09 AM', '9am'
          - '9:00', '09:00'
          - '3 PM', '3pm'
          - '15:30'
        Converts all formats to 'HH:MM AM/PM'.
        """
        try:
            parsed = parser.parse(v, fuzzy=True)
        except Exception:
            raise ValueError(
                f"Invalid time format: {v}. Please provide a valid time like 9 AM or 10:30 AM."
            )
        return parsed.strftime("%I:%M %p")

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if v is None:
            raise ValueError("Phone number is required.")
        pattern = re.compile(r"^[6-9]\d{9}$")
        if not pattern.match(v):
            raise ValueError(
                "Invalid phone number format. Must be a 10-digit Indian mobile number starting with 6-9."
            )
        return v


class RescheduleRequest(BaseModel):
    """
    Data needed to reschedule an existing appointment.
    The LLM should collect:
      - new_preferred_date
      - new_time
      - contact_email (used to locate existing appointment)
    """
    new_preferred_date: str = Field(..., description="New date in DD-MM-YYYY or natural language")
    new_time: str = Field(..., description="New time, flexible format")
    contact_email: EmailStr = Field(..., description="Email used when booking the appointment")

    @field_validator("new_preferred_date")
    @classmethod
    def validate_new_date(cls, v: str) -> str:
        now = datetime.now()
        s = _normalize_input(v)

        try:
            dt = parser.parse(s, dayfirst=True, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse date '{v}': {e}")

        candidate = dt.replace(year=now.year)
        if candidate.date() <= now.date():
            candidate = candidate.replace(year=now.year + 1)
        dt = candidate

        if dt.date() <= now.date():
            raise ValueError("New appointment date must be after today's date.")

        return dt.strftime("%d-%m-%Y")

    @field_validator("new_time")
    @classmethod
    def validate_new_time(cls, v: str) -> str:
        try:
            parsed = parser.parse(v, fuzzy=True)
        except Exception:
            raise ValueError(f"Invalid time format: {v}. Please provide a valid time like 9 AM or 4 PM.")
        return parsed.strftime("%I:%M %p")


# ---------------------------------------------------------
#  Global details for /appointment endpoint
# ---------------------------------------------------------

appointmentDetails: Dict[str, Any] = {}


# ---------------------------------------------------------
#  Date/time helpers
# ---------------------------------------------------------

def parse_date_time(date_str: str, time_str: str) -> Tuple[datetime, datetime]:
    """
    Parse date + time strings into a timezone-aware datetime range in IST.
    Used by both booking and rescheduling.
    """
    combined = f"{date_str} {time_str}"
    dt = parser.parse(combined, dayfirst=True, fuzzy=True)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KOLKATA)
    else:
        dt = dt.astimezone(KOLKATA)

    end_dt = dt + timedelta(minutes=30)
    return dt, end_dt


def _parse_appointment_to_datetimes(appointment: Appointment) -> Tuple[datetime, datetime]:
    """
    Wrapper that uses Appointment.preferred_date + Appointment.time.
    """
    return parse_date_time(appointment.preferred_date, appointment.time)


# ---------------------------------------------------------
#  Agent setup
# ---------------------------------------------------------

load_dotenv()

openrouter_provider = OpenAIProvider(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

model = OpenAIChatModel("kwaipilot/kat-coder-pro:free", provider=openrouter_provider)

agent = Agent(
    model=model,
    system_prompt=(
        "You are a friendly and conversational dental assistant. "
        "Ask for only one piece of information at a time (e.g., first ask for their name, "
        "then email, then date, then time and service). "
        "Never list all questions together. "
        "Keep responses short, polite, and natural — like a human conversation.\n\n"
        "When the user clearly wants to BOOK a new appointment, call the `dental_booking_agent` tool "
        "with the collected details.\n"
        "When the user clearly wants to RESCHEDULE an existing appointment, call the "
        "`reschedule_appointment` tool instead, using their email to look up the existing booking.\n"
        "Never claim an appointment is booked or rescheduled unless the tool returns a success status.\n"
        "If the user says 'yes', figure out what they mean based on context. "
        "You should not deviate from dental topics and if the user inquires about other stuff "
        "except dental booking politely deny the request. "
        "Confirm the appointment with summary of the booking right after successful booking/rescheduling."
    ),
    retries=3,
)


# ---------------------------------------------------------
#  Tool: Book appointment (Pinecone + Google Calendar)
# ---------------------------------------------------------

@agent.tool
def dental_booking_agent(ctx: RunContext[None], appointment: Appointment) -> dict:
    """
    Books a dental appointment and returns a structured confirmation.

    - Parses date/time to real datetimes.
    - Checks Google Calendar availability.
    - Creates event in Google Calendar.
    - Saves user + appointment in Pinecone.
    - Updates appointmentDetails (in-memory).
    """
    print(">>> TOOL CALLED: dental_booking_agent")
    try:
        # 1) Parse to datetimes
        start_dt, end_dt = _parse_appointment_to_datetimes(appointment)

        patient_name = appointment.name
        reason = appointment.reason or "Dental appointment"

        # Build a user_id for persistence (prefer email)
        if appointment.contact_email:
            user_id = appointment.contact_email
        else:
            user_id = f"user:{patient_name}:{appointment.contact_phone}"

        # 2) Check Google Calendar slot
        if not is_slot_free(start_dt, end_dt):
            msg = (
                f"❌ Sorry {patient_name}, that time slot on {appointment.preferred_date} "
                f"at {appointment.time} is already booked. "
                "Would you like to try a different time on the same date, or choose a different date?"
            )
            return {"status": "unavailable", "message": msg}

        # 3) Create StoredAppointment for persistence
        stored = StoredAppointment(
            id=str(uuid.uuid4()),
            user_id=user_id,
            patient_name=patient_name,
            reason=reason,
            start_time=start_dt,
            end_time=end_dt,
            status="confirmed",
        )

        # 4) Create event in Google Calendar
        event_id = create_calendar_event(stored)
        stored.google_event_id = event_id

        # 5) Save user profile if we have email
        if appointment.contact_email:
            profile = UserProfile(
                user_id=user_id,
                name=patient_name,
                email=appointment.contact_email,
                phone=appointment.contact_phone,
            )
            save_user(profile)

        # 6) Save appointment to Pinecone
        save_stored_appointment(stored)

        # 7) Update in-memory details
        global appointmentDetails
        appointmentDetails["name"] = appointment.name
        appointmentDetails["date"] = appointment.preferred_date
        appointmentDetails["time"] = appointment.time
        appointmentDetails["reason"] = appointment.reason
        appointmentDetails["phone"] = appointment.contact_phone
        appointmentDetails["email"] = appointment.contact_email
        appointmentDetails["start_time"] = start_dt.isoformat()
        appointmentDetails["end_time"] = end_dt.isoformat()
        appointmentDetails["google_event_id"] = event_id
        appointmentDetails["user_id"] = user_id

        local_time_str = start_dt.strftime("%d-%m-%Y at %I:%M %p")
        confirmation = (
            "✅ Appointment booked!\n"
            f"Name: {appointment.name}\n"
            f"Date: {appointment.preferred_date}\n"
            f"Time: {appointment.time}\n"
            f"Reason: {appointment.reason}\n\n"
            f"Your appointment is confirmed on {local_time_str}. "
            "It has been added to the clinic's calendar."
        )

        return {"status": "confirmed", "message": confirmation}

    except Exception as e:
        print(">>> dental_booking_agent ERROR:", repr(e))
        return {
            "status": "error",
            "message": f"Sorry, I couldn't book your appointment due to an internal error: {e}",
        }


# ---------------------------------------------------------
#  Tool: Reschedule appointment
# ---------------------------------------------------------

@agent.tool
def reschedule_appointment(ctx: RunContext[None], req: RescheduleRequest) -> dict:
    """
    Reschedules the user's latest upcoming confirmed appointment to a new date/time.

    - Finds the nearest upcoming confirmed appointment for the given email.
    - Moves the Google Calendar event (update, not create).
    - Updates the existing record in Pinecone (same id).
    - Returns a human-friendly confirmation message.
    """
    print(">>> TOOL CALLED: reschedule_appointment")
    try:
        user_id = req.contact_email

        # 1) Find existing appointment for this user
        existing = get_latest_confirmed_future_appointment(user_id)
        if not existing:
            return {
                "status": "not_found",
                "message": (
                    "I couldn't find any upcoming confirmed appointment for that email. "
                    "Please confirm which appointment you want to change."
                ),
            }

        # 2) Parse new datetimes directly (no Appointment model, so no phone required)
        new_start, new_end = parse_date_time(req.new_preferred_date, req.new_time)
        old_start = existing.start_time

        # 3) Update the existing appointment object
        existing.start_time = new_start
        existing.end_time = new_end

        # 4) Move the Google Calendar event
        if existing.google_event_id:
            update_calendar_event(existing)
        else:
            # If for some reason the old record had no event id, create one now
            event_id = create_calendar_event(existing)
            existing.google_event_id = event_id

        # 5) Save updated appointment back to Pinecone (upsert on same id)
        save_stored_appointment(existing)

        # 6) Update in-memory appointmentDetails
        global appointmentDetails
        appointmentDetails["name"] = existing.patient_name
        appointmentDetails["date"] = existing.start_time.strftime("%d-%m-%Y")
        appointmentDetails["time"] = existing.start_time.strftime("%I:%M %p")
        appointmentDetails["reason"] = existing.reason
        appointmentDetails["email"] = user_id
        appointmentDetails["start_time"] = existing.start_time.isoformat()
        appointmentDetails["end_time"] = existing.end_time.isoformat()
        appointmentDetails["google_event_id"] = existing.google_event_id
        appointmentDetails["user_id"] = user_id

        old_str = old_start.strftime("%d-%m-%Y at %I:%M %p")
        new_str = new_start.strftime("%d-%m-%Y at %I:%M %p")

        message = (
            "✅ Your appointment has been rescheduled.\n"
            f"Previous: {old_str}\n"
            f"New: {new_str}\n"
            f"Reason: {existing.reason}"
        )

        return {"status": "rescheduled", "message": message}

    except Exception as e:
        print(">>> reschedule_appointment ERROR:", repr(e))
        return {
            "status": "error",
            "message": f"Sorry, I couldn't reschedule your appointment due to an internal error: {e}",
        }


# ---------------------------------------------------------
#  Tool: Slot checker (calendar-based, matches main.py)
# ---------------------------------------------------------

@agent.tool_plain
def check_appointment_slot_available(appointment: Appointment) -> str:
    """
    Checks if a given slot is free using Google Calendar.
    Used by your /check_slot endpoint (which passes an Appointment model).
    """
    try:
        start_dt, end_dt = _parse_appointment_to_datetimes(appointment)
        if is_slot_free(start_dt, end_dt):
            return (
                f"The requested time slot on {appointment.preferred_date} at {appointment.time} "
                "is available for booking."
            )
        else:
            return (
                f"The requested time slot on {appointment.preferred_date} at {appointment.time} "
                "is NOT available. Please choose another time."
            )
    except Exception as e:
        return f"Sorry, I couldn't check the slot due to an internal error: {e}"


# ---------------------------------------------------------
#  CLI chat loop (optional)
# ---------------------------------------------------------

if __name__ == "__main__":
    print(" hey, how can I help you? ")
    exit_conditions = (":q", "quit", "exit", "bye")

    msg_history: list[dict[str, Any]] = []

    while True:
        query = input("> ")
        if query in exit_conditions:
            break
        else:
            result = agent.run_sync(query, message_history=msg_history)
            msg_history = result.all_messages()
            print(result.output)

    print(" Bye ")
