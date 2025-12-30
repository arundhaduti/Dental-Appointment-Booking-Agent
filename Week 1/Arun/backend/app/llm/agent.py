from __future__ import annotations
import tiktoken
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple, Optional, List

from dateutil import parser
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, EmailStr
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from datetime import datetime


from app.models import StoredAppointment, UserProfile
from app.persistence import (
    save_stored_appointment,
    save_user,
    get_latest_confirmed_future_appointment,
    _clean_metadata,
    get_user_metadata,
    DUMMY_VECTOR

)
from app.pinecone_client import index
from app.google_calendar import (
    is_slot_free,
    create_calendar_event,
    update_calendar_event,
    cancel_calendar_event,
    find_alternative_slots,
)


#  ------------------------------------------------------
#   To measure tokens
#  ------------------------------------------------------
def count_tokens(text: str, model: str = "gpt-4") -> int:
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


# ---------------------------------------------------------
#  Timezone setup
# ---------------------------------------------------------
try:
    from zoneinfo import ZoneInfo
    KOLKATA = ZoneInfo("Asia/Kolkata")
except Exception:
    KOLKATA = timezone(timedelta(hours=5, minutes=30))

# Today's date in IST, used for prompt anchoring
TODAY_IST = datetime.now(KOLKATA)
TODAY_IST_STR = TODAY_IST.strftime("%d-%m-%Y")
TODAY_IST_VERBOSE = TODAY_IST.strftime("%d %B %Y")


# ---------------------------------------------------------
#  Clinic working hours (IST)
# ---------------------------------------------------------
CLINIC_OPEN_HOUR = 9    # 9:00
CLINIC_LUNCH_START = 13 # 13:00 (1 PM)
CLINIC_LUNCH_END = 14   # 14:00 (2 PM)
CLINIC_CLOSE_HOUR = 18  # 18:00 (6 PM)


def is_within_working_hours(dt: datetime) -> bool:
    """
    Return True if the given datetime (any timezone) falls within
    clinic working hours in Asia/Kolkata, excluding lunch break.
    """
    local = dt.astimezone(KOLKATA)
    h = local.hour + local.minute / 60.0

    if h < CLINIC_OPEN_HOUR or h >= CLINIC_CLOSE_HOUR:
        return False

    # Exclude lunch break
    if CLINIC_LUNCH_START <= h < CLINIC_LUNCH_END:
        return False

    return True


def _normalize_input(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s)
    s = s.replace(",", "")
    return s


# ---------------------------------------------------------
#  Tracks how many times the user sent inappropriate content
# ---------------------------------------------------------
_violation_state: Dict[str, int] = {"count": 0}


def reset_violation_state() -> None:
    """
    Reset the moderation violation counter.
    Call this from /reset so new sessions start clean.
    """
    _violation_state["count"] = 0


# ---------------------------------------------------------
# Natural date resolver (fallback safety net)
# ---------------------------------------------------------
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}


def resolve_natural_date_phrase(s: str, now: datetime) -> Optional[datetime]:
    """
    Resolve simple natural-language date phrases into a datetime (same time-of-day as 'now')
    Returns a datetime or None if it cannot resolve.

    Handles:
      - today
      - tomorrow
      - day after tomorrow
      - in N days
      - next <weekday>
      - weekday names (upcoming)
    """
    if not s:
        return None
    s = s.strip().lower()

    if s == "today":
        return now
    if s == "tomorrow":
        return now + timedelta(days=1)
    if s in ("day after tomorrow", "day after", "dayaftertomorrow"):
        return now + timedelta(days=2)

    m = re.search(r"\bin\s+(\d{1,3})\s+days?\b", s)
    if m:
        days = int(m.group(1))
        return now + timedelta(days=days)

    m2 = re.search(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", s)
    if m2:
        weekday = WEEKDAYS[m2.group(1)]
        days_ahead = (weekday - now.weekday() + 7) % 7
        days_ahead = days_ahead if days_ahead != 0 else 7
        return now + timedelta(days=days_ahead)

    m3 = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", s)
    if m3:
        weekday = WEEKDAYS[m3.group(1)]
        days_ahead = (weekday - now.weekday() + 7) % 7
        if days_ahead == 0:
            days_ahead = 7
        return now + timedelta(days=days_ahead)

    return None


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

    # Preferences (explicit statements only)
    preferred_times: List[str] = Field(default_factory=list)
    preferred_dentist: Optional[str] = None
    insurance_provider: Optional[str] = None

    # Comfort & communication preferences
    dental_anxiety: Optional[bool] = None
    prefers_brief_responses: Optional[bool] = None
    prefers_emojis: Optional[bool] = None
    tone: Optional[str] = None  # 'formal' | 'friendly'

    # Metadata
    last_updated: datetime = Field(default_factory=lambda: datetime.now(KOLKATA))

    @field_validator("preferred_date")
    @classmethod
    def validate_preferred_date(cls, v: str) -> str:
        # Always interpret relative dates like 'tomorrow' in IST with helper, else parse.
        now = datetime.now(KOLKATA)
        s = _normalize_input(v)

        # 1) Try resolver (handles 'tomorrow', 'in 3 days', weekdays, etc.)
        resolved = resolve_natural_date_phrase(s, now)
        if resolved is not None:
            # enforce appointments must be after today
            if resolved.date() <= now.date():
                raise ValueError("Appointment date must be after today's date.")
            return resolved.strftime("%d-%m-%Y")

        # 2) Fallback to parser.parse
        try:
            dt = parser.parse(s, dayfirst=True, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse date '{v}': {e}")

        candidate = dt.replace(year=now.year)
        if candidate.date() <= now.date():
            candidate = candidate.replace(year=now.year + 1)
        dt = candidate

        if dt.date() <= now.date():
            raise ValueError("Appointment date must be after today's date.")

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
        now = datetime.now(KOLKATA)
        s = _normalize_input(v)

        # Try natural resolver first
        resolved = resolve_natural_date_phrase(s, now)
        if resolved is not None:
            if resolved.date() <= now.date():
                raise ValueError("New appointment date must be after today's date.")
            return resolved.strftime("%d-%m-%Y")

        # Fallback to parser.parse
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


class CancelRequest(BaseModel):
    """
    Data needed to cancel an existing appointment.
    For now, we cancel the nearest upcoming confirmed appointment for this email.
    """
    contact_email: EmailStr = Field(..., description="Email used when booking the appointment")


class GetAppointmentRequest(BaseModel):
    """
    Data needed to look up an existing appointment.
    For now we return the nearest upcoming confirmed appointment for this email.
    """
    contact_email: EmailStr = Field(..., description="Email used when booking the appointment")


class ModerationRequest(BaseModel):
    """
    Used when the assistant detects inappropriate content.
    'reason' is a short description such as 'sexual content', 'harassment', etc.
    """
    reason: str = Field(..., description="Why the message is inappropriate (e.g. 'sexual content', 'harassment').")


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

# System prompt: NOTE we now require the LLM to convert relative dates into DD-MM-YYYY before calling tools.
sys_prompt = (
    "You are a friendly, concise dental assistant. Ask only one piece of information at a time "
    "(e.g., name → email → phone → date → time → service); NEVER list all questions at once. Keep replies short, "
    "polite and natural. Do NOT assume any information.\n"
    "When the user explicitly states a preference or personal detail (for example: “I prefer evening appointments”, “I like brief responses”, “I'm anxious about dental visits”),"
    "you MUST populate the corresponding preference fields in the Appointment object (preferred_times, dental_anxiety, prefers_brief_responses, prefers_emojis, tone, etc.)"
    "while continuing the current booking or scheduling flow. Do NOT pause the flow, do NOT ask for confirmation to store preferences, and do NOT mention memory or saving. Only store preferences that the user states explicitly."
    "ALWAYS look for such preferences in every user message and update the Appointment object accordingly.\n"
    f"Today is {TODAY_IST_VERBOSE} in Asia/Kolkata. "
    "IMPORTANT: When the user gives a relative or natural-language date (e.g. 'today', 'tomorrow', "
    "'day after tomorrow', 'in 3 days', 'next Monday', 'Monday'), you MUST convert it to an explicit "
    "DD-MM-YYYY value (Asia/Kolkata) before calling any tool that accepts a date (preferred_date or new_preferred_date). "
    f"Examples using today = {TODAY_IST_STR}: 'today' -> '{TODAY_IST_STR}'; 'tomorrow' -> (tomorrow's DD-MM-YYYY); "
    "'day after tomorrow' -> (DD-MM-YYYY for +2 days). Always use the explicit DD-MM-YYYY string in tool call payloads and in user confirmations.\n\n"
    "If the user wants to BOOK, call dental_booking_agent with collected details. If that tool returns "
    "'unavailable' with alternatives, present those suggested slots and ask the user to pick one; do NOT "
    "ask the user to invent new dates/times.\n"
    "If the user asks about their preferences, call get_user_preferences using their email."
    "If the user wants to RESCHEDULE, call reschedule_appointment using their email to find the booking.\n"
    "Clinic hours (IST): 9:00-13:00 and 14:00-18:00. Do NOT suggest or book outside these hours or during "
    "lunch (13:00-14:00). If asked for an outside time, explain the hours and offer valid times.\n"
    "If the user wants to CANCEL, call cancel_appointment with their email. To VIEW/CHECK an appointment, call "
    "get_appointment_details with their email.\n"
    "Never claim an appointment is booked, rescheduled, cancelled, or retrieved unless the corresponding tool "
    "returns success. If the user says 'yes', infer intent from context. Restrict to dental booking topics; "
    "politely refuse unrelated requests. After successful booking/rescheduling, confirm with a summary.\n\n"
    "After a booking is confirmed, if the user mentions a new preference (e.g., dental anxiety, tone, emoji usage, preferred dentist, preferred times), update preferences only using update_user_preferences."
    "Do not check availability or modify the appointment unless the user explicitly asks to change the date or time."
    "If a user message contains sexual content, harassment, abusive language, explicit or inappropriate statements, or "
    "violent or hateful speech, you must not answer it or call any booking tools. Instead, call the `moderation_guard` tool "
    "with a short reason (e.g., 'sexual content', 'harassment', 'violence'). Use only the message returned by that tool as your reply. "
    "If the tool indicates that the conversation is ended due to repeated violations, you must not respond with anything "
    "else and must repeat only that boundary message until the user returns to appropriate dental-booking questions.\n"
    "If the user enters an invalid date, do not call the 'moderation_guard' tool; instead, politely inform them that the date is invalid and ask them to provide a valid date."
)

agent = Agent(
    model=model,
    system_prompt=sys_prompt,
    retries=3,
)

# Before optimization
old_prompt_tokens = count_tokens(sys_prompt)
print(f"Current token usage is: {old_prompt_tokens} tokens per request")


# ---------------------------------------------------------
#  Tool: moderation_guard
# ---------------------------------------------------------
@agent.tool
def moderation_guard(ctx: RunContext[None], req: ModerationRequest) -> dict:
    """
    Called by the LLM whenever it detects inappropriate content in the user's message.

    It:
      - Increments an internal violation counter.
      - Returns a message the assistant should send back.
      - Signals when the conversation should effectively be "ended".
    """
    print(">>> TOOL CALLED: moderation_guard")
    _violation_state["count"] += 1
    count = _violation_state["count"]

    if count == 1:
        message = (
            "I can’t respond to that.\n"
            "I’m here to help you book a dental appointment.\n"
            "When would you like to schedule your visit?"
        )
        status = "warn"
        end_conversation = False

    elif count == 2:
        message = (
            "I’m only able to assist with dental appointment bookings.\n"
            "Please keep the conversation appropriate.\n"
            "When would you like your dental appointment?"
        )
        status = "warn"
        end_conversation = False

    else:
        # 🔒 Add a special marker so the UI knows the conversation is locked
        message = (
            "[CONVERSATION_LOCKED]\n"
            "I can only assist with dental appointment bookings and will not continue this "
            "conversation while you send inappropriate messages."
        )
        status = "blocked"
        end_conversation = True

    return {
        "status": status,
        "message": message,
        "violation_count": count,
        "end_conversation": end_conversation,
        "reason": req.reason,
    }




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
    # DEBUG: show exactly what the LLM passed to the tool
    print("TOOL INPUT:", appointment.preferred_date, appointment.time)
    try:
        # 1) Parse to datetimes
        start_dt, end_dt = _parse_appointment_to_datetimes(appointment)

        patient_name = appointment.name
        reason = appointment.reason or "Dental appointment"

        # 1.5) Enforce clinic working hours
        if not (is_within_working_hours(start_dt) and is_within_working_hours(end_dt)):
            hours_msg = (
                "Our clinic operates from 9:00 AM to 1:00 PM and from 2:00 PM to 6:00 PM, "
                "and we do not book appointments during the lunch break (1:00 PM – 2:00 PM)."
            )
            msg = (
                f"❌ The requested time on {appointment.preferred_date} at {appointment.time} "
                "is outside our working hours or during our lunch break.\n\n"
                f"{hours_msg}\n"
                "Please choose a time within these hours."
            )
            return {"status": "outside_hours", "message": msg}

        # Build a user_id for persistence (prefer email)
        if appointment.contact_email:
            user_id = appointment.contact_email
        else:
            user_id = f"user:{patient_name}:{appointment.contact_phone}"

        # 2) Check Google Calendar slot
        if not is_slot_free(start_dt, end_dt):
            # Find nearby alternative slots
            alternatives = find_alternative_slots(start_dt, duration_minutes=30, max_suggestions=4)

            if alternatives:
                lines = []
                alt_structs = []

                for alt_start, alt_end in alternatives:
                    alt_local = alt_start.astimezone(KOLKATA)
                    date_display = alt_local.strftime("%d-%m-%Y")
                    time_display = alt_local.strftime("%I:%M %p")

                    lines.append(f"* {date_display} — {time_display}")
                    alt_structs.append(
                        {
                            "start_time": alt_start.isoformat(),
                            "end_time": alt_end.isoformat(),
                            "date_display": date_display,
                            "time_display": time_display,
                        }
                    )

                msg = (
                    f"❌ Sorry {patient_name}, that time slot on {appointment.preferred_date} "
                    f"at {appointment.time} is already booked.\n\n"
                    "Here are the closest available times:\n"
                    + "\n".join(lines)
                    + "\n\nWhich one would you like to book?"
                )

                # The LLM will see this message and should ask the user to pick one
                return {
                    "status": "unavailable",
                    "message": msg,
                    "alternatives": alt_structs,
                }

            # Fallback: no alternatives found
            msg = (
                f"❌ Sorry {patient_name}, that time slot on {appointment.preferred_date} "
                f"at {appointment.time} is already booked, and I couldn't find any nearby free slots. "
                "Would you like to try a different date?"
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
            save_user(profile,
                    preferences={
                        "preferred_times": appointment.preferred_times,
                        "preferred_dentist": appointment.preferred_dentist,
                        "insurance_provider": appointment.insurance_provider,
                        "dental_anxiety": appointment.dental_anxiety,
                        "prefers_brief_responses": appointment.prefers_brief_responses,
                        "prefers_emojis": appointment.prefers_emojis,
                        "tone": appointment.tone,
                        "last_updated": appointment.last_updated.isoformat(),
    })

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

        # 2) Parse new datetimes directly
        new_start, new_end = parse_date_time(req.new_preferred_date, req.new_time)
        old_start = existing.start_time

        # 2.5) Enforce clinic working hours for reschedule
        if not (is_within_working_hours(new_start) and is_within_working_hours(new_end)):
            hours_msg = (
                "Our clinic operates from 9:00 AM to 1:00 PM and from 2:00 PM to 6:00 PM, "
                "and we do not book appointments during the lunch break (1:00 PM – 2:00 PM)."
            )
            msg = (
                "The new requested time is outside our working hours or during our lunch break.\n\n"
                f"{hours_msg}\n"
                "Please choose a time within these hours."
            )
            return {"status": "outside_hours", "message": msg}

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
#  Tool: Cancel appointment
# ---------------------------------------------------------
@agent.tool
def cancel_appointment(ctx: RunContext[None], req: CancelRequest) -> dict:
    """
    Cancels the user's nearest upcoming confirmed appointment.
    """
    print(">>> TOOL CALLED: cancel_appointment")
    try:
        user_id = req.contact_email

        # 1) Find existing upcoming confirmed appointment
        existing = get_latest_confirmed_future_appointment(user_id)
        if not existing:
            return {
                "status": "not_found",
                "message": (
                    "I couldn't find any upcoming confirmed appointment for that email. "
                    "If you think there should be one, please double-check the email you used when booking."
                ),
            }

        # 2) Cancel the calendar event (soft-fail if it errors)
        cancel_calendar_event(existing)

        # 3) Mark as cancelled in persistence
        existing.status = "cancelled"
        save_stored_appointment(existing)

        # 4) Update in-memory appointmentDetails
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
        appointmentDetails["status"] = "cancelled"

        when_str = existing.start_time.strftime("%d-%m-%Y at %I:%M %p")
        message = (
            "✅ Your appointment has been cancelled.\n"
            f"Cancelled appointment was scheduled for {when_str}.\n"
            "If you’d like, I can help you book a new time."
        )

        return {"status": "cancelled", "message": message}

    except Exception as e:
        print(">>> cancel_appointment ERROR:", repr(e))
        return {
            "status": "error",
            "message": f"Sorry, I couldn't cancel your appointment due to an internal error: {e}",
        }


# ---------------------------------------------------------
#  Tool: Get appointment details
# ---------------------------------------------------------
@agent.tool
def get_appointment_details(ctx: RunContext[None], req: GetAppointmentRequest) -> dict:
    """
    Returns the nearest upcoming confirmed appointment for this email, if any.
    """
    print(">>> TOOL CALLED: get_appointment_details")
    try:
        user_id = req.contact_email

        existing = get_latest_confirmed_future_appointment(user_id)
        if not existing:
            return {
                "status": "not_found",
                "message": (
                    "I couldn't find any upcoming confirmed appointment for that email. "
                    "If you think you have a booking, please double-check the email you used."
                ),
            }

        # Build a clean, serializable representation
        start_local = existing.start_time.astimezone(KOLKATA)
        end_local = existing.end_time.astimezone(KOLKATA)

        result = {
            "status": "found",
            "appointment_id": existing.id,
            "patient_name": existing.patient_name,
            "reason": existing.reason,
            "status_value": existing.status,
            "start_time": start_local.isoformat(),
            "end_time": end_local.isoformat(),
            "date_display": start_local.strftime("%d-%m-%Y"),
            "time_display": start_local.strftime("%I:%M %p"),
            "google_event_id": existing.google_event_id,
            "user_id": existing.user_id,
        }

        # Optionally also update in-memory appointmentDetails so /appointment reflects this
        global appointmentDetails
        appointmentDetails["name"] = existing.patient_name
        appointmentDetails["date"] = result["date_display"]
        appointmentDetails["time"] = result["time_display"]
        appointmentDetails["reason"] = existing.reason
        appointmentDetails["email"] = user_id
        appointmentDetails["start_time"] = result["start_time"]
        appointmentDetails["end_time"] = result["end_time"]
        appointmentDetails["google_event_id"] = existing.google_event_id
        appointmentDetails["user_id"] = existing.user_id
        appointmentDetails["status"] = existing.status

        # Human-friendly summary the LLM can echo
        summary = (
            "Here are your upcoming appointment details:\n"
            f"- Name: {existing.patient_name}\n"
            f"- Date: {result['date_display']}\n"
            f"- Time: {result['time_display']}\n"
            f"- Reason: {existing.reason}\n"
            f"- Status: {existing.status}"
        )

        result["message"] = summary
        return result

    except Exception as e:
        print(">>> get_appointment_details ERROR:", repr(e))
        return {
            "status": "error",
            "message": f"Sorry, I couldn't fetch your appointment details due to an internal error: {e}",
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
    


@agent.tool
def update_user_preferences(ctx: RunContext[None], profile: dict) -> dict:
    """
    Update existing user preference fields only.
    LLM should provide:
      - contact_email (search key)
      - ONLY the changed preference fields.
    """
    try:
        email = profile.get("contact_email")
        if not email:
            return {
                "status": "error",
                "message": "Missing contact email to locate user profile."
            }

        # Fetch existing user metadata first
        existing = get_user_metadata(email)
        if not existing:
            return {
                "status": "not_found",
                "message": "I couldn't update preferences because I couldn't find your profile."
            }

        # Merge updated preference fields
        updated_prefs = {
            k: v for k, v in profile.items()
            if k not in ("contact_email", "type", "user_id") and v is not None
        }

        existing.update(updated_prefs)

        
        # Remove fields like "None" → treat as null
        for k in list(existing.keys()):
            if isinstance(existing[k], str) and existing[k].strip().lower() == "none":
                del existing[k]

        cleaned = _clean_metadata(existing)
        print(">>> UPSERT DATA:", cleaned)

        index.upsert(
        vectors=[
            {
                "id": f"user-{email}",
                "values": DUMMY_VECTOR,
                "metadata": cleaned,
            }
        ],
        namespace="users",
    )



        print(">>> User preferences updated:", updated_prefs)

        return {
            "status": "updated",
            "message": "Thanks! I’ve updated your preferences."
        }

    except Exception as e:
        print(">>> update_user_preferences ERROR:", repr(e))
        return {
            "status": "error",
            "message": f"Preference update failed: {e}"
        }


from pydantic import BaseModel, EmailStr


class GetPreferencesRequest(BaseModel):
    contact_email: EmailStr


@agent.tool
def get_user_preferences(ctx: RunContext[None], req: GetPreferencesRequest) -> dict:
    """
    Returns stored user preference fields for the email provided.
    """
    try:
        email = req.contact_email
        metadata = get_user_metadata(email)

        if not metadata:
            return {
                "status": "not_found",
                "message": "I couldn’t find any saved preferences for that email yet."
            }

        # Extract preference-specific fields only
        preference_keys = [
            "preferred_times",
            "preferred_dentist",
            "insurance_provider",
            "dental_anxiety",
            "prefers_brief_responses",
            "prefers_emojis",
            "tone"
        ]

        prefs = {k: v for k, v in metadata.items() if k in preference_keys and v is not None}

        if not prefs:
            return {
                "status": "no_preferences",
                "message": "You don’t have any specific preferences saved yet."
            }

        # Build a friendly-tone summary message
        summary_lines = []
        for key, value in prefs.items():
            label = key.replace("_", " ").capitalize()
            summary_lines.append(f"- {label}: {value}")

        summary = "Here are your saved dental care preferences:\n" + "\n".join(summary_lines)

        return {
            "status": "found",
            "preferences": prefs,
            "message": summary
        }

    except Exception as e:
        print(">>> get_user_preferences ERROR:", repr(e))
        return {
            "status": "error",
            "message": f"Could not retrieve preferences: {e}"
        }



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
