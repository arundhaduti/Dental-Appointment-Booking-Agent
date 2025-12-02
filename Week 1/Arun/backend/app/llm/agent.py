from pydantic import BaseModel, Field, field_validator, EmailStr
from pydantic_ai import Agent, RunContext
from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import re
from dateutil import parser
import uuid
from typing import Any, Dict

# Week 3 imports (Pinecone + Google Calendar)
from app.models import StoredAppointment, UserProfile
from app.persistence import save_stored_appointment, save_user
from app.google_calendar import is_slot_free, create_calendar_event
from typing import Any, Dict

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
from app.models import StoredAppointment, UserProfile


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
    s = re.sub(r'(\d+)(st|nd|rd|th)\b', r'\1', s)
    s = s.replace(',', '')
    return s


# ---------------------------------------------------------
#  Define Appointment Schema (Week 1)
# ---------------------------------------------------------

class Appointment(BaseModel):
    name: str = Field(..., description="Patient's full name")
    preferred_date: str = Field(..., description="Appointment date in DD-MM-YYYY format")
    time: str = Field(..., description="Appointment time, e.g., 10:30 AM")
    reason: str = Field(..., description="Reason for visit, e.g., Cleaning, Check-up, etc.")
    contact_email: EmailStr | None = None
    contact_phone: str = Field(..., description="10 digit phone number")

    @field_validator('preferred_date')
    @classmethod
    def validate_preferred_date(cls, v: str) -> str:
        """
        Your existing natural-language date parsing logic, preserved.
        - Accepts things like "5th Jan", "15 August", etc.
        - Normalizes into DD-MM-YYYY
        - Ensures appointment date is in the future (not today or past).
        """
        now = datetime.now()
        s = _normalize_input(v)

        try:
            dt = parser.parse(s, dayfirst=True, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse date '{v}': {e}")

        # Always push to this year, then next if needed
        candidate = dt.replace(year=now.year)
        if candidate.date() <= now.date():
            candidate = candidate.replace(year=now.year + 1)
        dt = candidate

        if dt.date() <= now.date():
            raise ValueError("Appointment date must be after today's date.")

        return dt.strftime("%d-%m-%Y")

    # ✅ Validate phone number format (unchanged)
    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v
        pattern = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit number starting 6–9
        if not pattern.match(v):
            raise ValueError(
                "Invalid phone number format. Must be a 10-digit Indian mobile number starting with 6-9."
            )
        return v


class RescheduleRequest(BaseModel):
    """
    Data needed to reschedule an existing appointment for a user.
    The LLM should collect the new date & time and the email (user id).
    """
    new_preferred_date: str = Field(..., description="New date in DD-MM-YYYY format")
    new_time: str = Field(..., description="New time, e.g., 10:30 AM")
    contact_email: EmailStr = Field(..., description="Email used to identify the existing appointment")

    @field_validator("new_preferred_date")
    @classmethod
    def validate_new_date(cls, v: str) -> str:
        # You can reuse your existing logic; for now we apply the same parsing rules
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


# ---------------------------------------------------------
#  Agent setup (Week 1)
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
        "Keep responses short, polite, and natural — like a human conversation. "
        "When the user clearly wants to BOOK a new appointment, call the `dental_booking_agent` tool "
        "with the collected details. "
        "When the user clearly wants to RESCHEDULE an existing appointment, call the "
        "`reschedule_appointment` tool instead, using their email to look up the existing booking. "
        "Never claim an appointment is booked or rescheduled unless the tool returns a success status. "
        "If the user says 'yes', figure out what they mean based on context. "
        "You should not deviate from dental topics and if the user inquires about other stuff "
        "except dental booking politely deny the request."
    ),
    retries=3,
)


# ---------------------------------------------------------
#  Globals (Week 1)
# ---------------------------------------------------------

appointmentSlots = {
    "9:00AM": "Available",
    "10:00AM": "Available",
    "11:30AM": "Available",
    "12:00AM": "Available",
    "1:00PM": "Available",
    "2:00PM": "Available",
    "4:00PM": "Available",
    "5:00PM": "Available",
    "6:00AM": "Available",
    "7:00AM": "Available"
}

appointmentDetails: Dict[str, Any] = {}


# ---------------------------------------------------------
#  Helper: parse Appointment -> datetimes (Week 3)
# ---------------------------------------------------------

def _parse_appointment_to_datetimes(appointment: Appointment) -> tuple[datetime, datetime]:
    """
    Convert the Week 1 Appointment (preferred_date + time)
    into timezone-aware datetimes in Asia/Kolkata.
    - preferred_date: DD-MM-YYYY
    - time: 'HH:MM' or 'HH:MM AM/PM'
    """
    # Parse the normalized date (we already ensured DD-MM-YYYY)
    day, month, year = map(int, appointment.preferred_date.split("-"))

    # Parse time in either 24h or 12h format
    time_str = appointment.time.strip().upper()
    parsed_time = None
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            parsed_time = datetime.strptime(time_str, fmt).time()
            break
        except ValueError:
            continue

    if parsed_time is None:
        raise ValueError(
            f"Invalid time format (expected 'HH:MM' or 'HH:MM AM/PM'): {appointment.time}"
        )

    start_dt = datetime(
        year,
        month,
        day,
        parsed_time.hour,
        parsed_time.minute,
        tzinfo=KOLKATA,
    )

    # default duration: 30 minutes
    end_dt = start_dt + timedelta(minutes=30)
    return start_dt, end_dt


# ---------------------------------------------------------
#  Tool: Book appointment (now calendar + Pinecone) (Week 3)
# ---------------------------------------------------------

@agent.tool
def dental_booking_agent(ctx: RunContext[None], appointment: Appointment) -> dict:
    """
    Books a dental appointment and returns a structured confirmation.

    Week 3 upgrade:
      - Parses date/time to real datetimes.
      - Checks Google Calendar availability.
      - Creates event in Google Calendar.
      - Saves user + appointment in Pinecone.
      - Updates appointmentDetails (in-memory).
    """
    print(">>> TOOL CALLED: dental_booking_agent")
    # 1) Parse to datetimes
    start_dt, end_dt = _parse_appointment_to_datetimes(appointment)

    patient_name = appointment.name
    reason = appointment.reason or "Dental appointment"

    # Build a user_id for persistence (prefer email)
    if appointment.contact_email:
        user_id = appointment.contact_email
    else:
        # fallback if no email is given
        user_id = f"user:{patient_name}:{appointment.contact_phone or ''}"

    # 2) Check Google Calendar slot
    if not is_slot_free(start_dt, end_dt):
        # We still return a dict, with a clear message
        msg = (
            f"❌ Sorry {patient_name}, that time slot on {appointment.preferred_date} "
            f"at {appointment.time} is already booked. Please choose another time."
        )
        return {"status": "unavailable", "message": msg}

    # 3) Create StoredAppointment object for persistence
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

    # 5) Save user profile to Pinecone if we have email
    if appointment.contact_email:
        profile = UserProfile(
            user_id=user_id,
            name=patient_name,
            email=appointment.contact_email,
            phone=appointment.contact_phone or None,
        )
        save_user(profile)

    # 6) Save appointment to Pinecone
    save_stored_appointment(stored)

    # 7) Update in-memory details (for /appointment endpoint)
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

    # 8) Human-readable confirmation (goes back into LLM + /book)
    local_time_str = start_dt.strftime("%d-%m-%Y at %I:%M %p")
    confirmation = (
        f"✅ Appointment booked!\n"
        f"Name: {appointment.name}\n"
        f"Date: {appointment.preferred_date}\n"
        f"Time: {appointment.time}\n"
        f"Reason: {appointment.reason}\n\n"
        f"Your appointment is confirmed on {local_time_str}. "
        f"It has been added to the clinic's calendar."
    )

    return {"status": "confirmed", "message": confirmation}


@agent.tool
def reschedule_appointment(ctx: RunContext[None], req: RescheduleRequest) -> dict:
    """
    Reschedules the user's latest upcoming confirmed appointment to a new date/time.

    - Finds the nearest upcoming confirmed appointment for the given email.
    - Moves the Google Calendar event (update, not create).
    - Updates the existing record in Pinecone (same id).
    - Returns a human-friendly confirmation message.
    """
    user_id = req.contact_email
    print(">>> TOOL CALLED: reschedule_appointment")
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

    # 2) Build a temporary Appointment-like object so we can reuse parsing logic
    temp_appointment = Appointment(
        name=existing.patient_name,
        preferred_date=req.new_preferred_date,
        time=req.new_time,
        reason=existing.reason,
        contact_email=user_id,
        contact_phone=None,
    )

    # 3) Parse new datetime range
    new_start, new_end = _parse_appointment_to_datetimes(temp_appointment)

    # Optional: if you want, check slot availability. For reschedule, you may skip this
    # or implement a version of is_slot_free that ignores the existing event.
    # if not is_slot_free(new_start, new_end):
    #     return {
    #         "status": "unavailable",
    #         "message": "That new time is not available. Please choose a different time.",
    #     }

    # 4) Update the existing appointment object
    old_start = existing.start_time
    old_end = existing.end_time

    existing.start_time = new_start
    existing.end_time = new_end
    # status stays "confirmed"
    # id and google_event_id remain the same

    # 5) Move the Google Calendar event
    if existing.google_event_id:
        update_calendar_event(existing)
    else:
        # If for some reason the old record had no event id, we can create one now
        event_id = create_calendar_event(existing)
        existing.google_event_id = event_id

    # 6) Save updated appointment back to Pinecone (upsert on same id)
    save_stored_appointment(existing)

    # 7) Optionally update your in-memory appointmentDetails for your /appointment endpoint
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
        f"✅ Your appointment has been rescheduled.\n"
        f"Previous: {old_str}\n"
        f"New: {new_str}\n"
        f"Reason: {existing.reason}"
    )

    return {"status": "rescheduled", "message": message}


# ---------------------------------------------------------
#  Tool: Simple slot checker (still toy / Week 1 style)
# ---------------------------------------------------------

@agent.tool_plain
def check_appointment_slot_available(time: str) -> str:
    """
    Week 1-style slot check.
    Still uses hard-coded appointmentSlots and only looks at time-of-day.
    This is kept as-is for compatibility with your existing /check_slot endpoint
    and any prompt logic that expects a simple time string.
    """
    if time not in appointmentSlots:
        available_slots = [t for t, status in appointmentSlots.items() if status == "Available"]
        return "Slot not available. Available slots are: " + ", ".join(available_slots)

    status = appointmentSlots[time]
    if status == "Available":
        return f"{time} is available for booking."
    else:
        return f"{time} is not available."


# ---------------------------------------------------------
#  CLI chat loop (unchanged, only for local testing)
# ---------------------------------------------------------
if __name__ == "__main__":
    print(" hey, how can I help you? ")
    exit_conditions = (":q", "quit", "exit", "bye")

    msg_history = []

    # Simple loop for interactive CLI chatbot
    while True:
        query = input("> ")
        if query in exit_conditions:
            break
        else:
            result = agent.run_sync(query, message_history=msg_history)
            msg_history = result.all_messages()
            print(result.output)

    print(" Bye ")
