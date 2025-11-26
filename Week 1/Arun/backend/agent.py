from pydantic import BaseModel, Field, field_validator, EmailStr
from pydantic_ai import Agent, RunContext
from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import re
from datetime import datetime
from dateutil import parser

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
#  Define Appointment Schema
# ---------------------------------------------------------




class Appointment(BaseModel):
    name: str = Field(..., description="Patient's full name")
    preferred_date: str = Field(..., description="Appointment date in DD-MM-YYYY format")
    time: str = Field(..., description="Appointment time, e.g., 10:30 AM")
    reason: str = Field(..., description="Reason for visit, e.g., Cleaning, Check-up, etc.")
    contact_email: EmailStr = None
    contact_phone: str = Field(..., description="10 digit phone number")




    # @field_validator('preferred_date')
    # @classmethod
    # def date_must_be_today_or_future(cls, value: str) -> str:
    #     try:
    #         # Parse the date string
    #         parsed_date = datetime.strptime(value, "%d-%m-%Y").date()
    #     except ValueError:
    #         raise ValueError("preferred_date must be in DD-MM-YYYY format")

    #     # Check if it's today or in the future
    #     if parsed_date < date.today():
    #         print(parsed_date)
    #         raise ValueError("Preferred date must be today or in the future")

    #     return value
        

    @field_validator('preferred_date')
    @classmethod
    def validate_preferred_date(cls, v: str) -> str:
        now = datetime.now()
        s = _normalize_input(v)

        try:
            dt = parser.parse(s, dayfirst=True, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse date '{v}': {e}")

        # if not re.search(r'\b\d{4}\b', s):
        #     candidate = dt.replace(year=now.year)
        #     if candidate.date() <= now.date():
        #         candidate = candidate.replace(year=now.year + 1)
        #     dt = candidate

        candidate = dt.replace(year=now.year)
        if candidate.date() <= now.date():
            candidate = candidate.replace(year=now.year + 1)
        dt = candidate
        

        if dt.date() <= now.date():
            raise ValueError("Appointment date must be after today's date.")

        return dt.strftime("%d-%m-%Y")
    
    # ✅ Validate phone number format
    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v  # optional
        pattern = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit number starting 6–9
        if not pattern.match(v):
            raise ValueError("Invalid phone number format. Must be a 10-digit Indian mobile number starting with 6-9.")
        return v


# ---------------------------------------------------------
#  Create Agent and Register Tool
# ---------------------------------------------------------

load_dotenv()

openrouter_provider = OpenAIProvider(base_url="https://openrouter.ai/api/v1",api_key=os.getenv("OPENROUTER_API_KEY"))

model = OpenAIChatModel('kwaipilot/kat-coder-pro:free',provider=openrouter_provider)

agent = Agent(
    model=model,  # You can use any supported model or local model
    system_prompt="You are a friendly and conversational dental assistant. "
        "Ask for **only one piece of information at a time** (e.g., first ask for their name,then email,then date, then time and service)"
        "Never list all questions together. "
        "Keep responses short, polite, and natural — like a human conversation. "
        "Once you have all details, call the appropriate tool yourself. "
        "If the user says 'yes', figure out what they mean based on context."
        "You should not deviate from dental topic and if the user inquire about other stuff except dental booking politely deny the request"
    ,
    retries=3
)


# ---------------------------------------------------------
#  Define Tool
# ---------------------------------------------------------

appointmentSlots = {'11:30AM':"Available",
                    '1:00PM':"Unavailable",
                    '2:00PM':"Available",
                    '4:00PM':"Unavailable",
                    '5:00PM':"Available"}

appointmentDetails = {}


@agent.tool
def dental_booking_agent(ctx: RunContext[None], appointment: Appointment) -> str:
    """
    Books a dental appointment and returns a structured confirmation.
    In a real implementation, this could save to a DB or calendar.
    """

    confirmation = (
        f"✅ Appointment booked!\n"
        f"Name: {appointment.name}\n"
        f"Date: {appointment.preferred_date}\n"
        f"Time: {appointment.time}\n"
        f"Reason: {appointment.reason}"
    )

    appointmentDetails['name'] = appointment.name
    appointmentDetails['date'] = appointment.preferred_date
    appointmentDetails['time'] = appointment.time
    appointmentDetails['reason'] = appointment.reason
    appointmentDetails['phone'] = appointment.contact_phone
    appointmentDetails['email'] = appointment.contact_email

    return {"status": "confirmed", "message": confirmation}




@agent.tool_plain
def check_appointment_slot_available(time: str) -> str:
    if time not in appointmentSlots:
        available_slots = [t for t, status in appointmentSlots.items() if status == "Available"]
        return "Slot not available. Available slots are: " + ", ".join(available_slots)

    status = appointmentSlots[time]
    if status == "Available":
        return f"{time} is available for booking."
    else:
        return f"{time} is not available."


# ---------------------------------------------------------
#  Run Conversation (LLM-driven)
# ---------------------------------------------------------
if __name__ == "__main__":
    
    print(" hey, how can I help you? ")
    exit_conditions = (":q", "quit", "exit", "bye")

    msg_history = []

    #Simple loop for interactive CLI chatbot
    while True:
        query = input("> ")
        if query in exit_conditions:
            break
        else:
            result = agent.run_sync(query, message_history=msg_history)
            msg_history = result.all_messages()
            print(result.output)

    print(" Bye ")