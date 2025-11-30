import os
import re
import asyncio
from datetime import date
from typing import Optional, Dict, Any

import dateparser
from pydantic import BaseModel, Field, EmailStr, field_validator
from dotenv import load_dotenv

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
# Load environment variables from .env file
load_dotenv()
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY")
PHONE_REGEX = re.compile(r"^\d{10}$")

class Appointment(BaseModel):
    user_name: str
    email: Optional[EmailStr] = None
    service: Optional[str] = None
    appointment_date: Optional[date] = None
    appointment_time: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("appointment_date", mode="before")
    def normalize_date(cls, v):
        parsed = dateparser.parse(v, settings={"PREFER_DATES_FROM": "future"})
        if not parsed:
            raise ValueError("Invalid or unclear date format.")
        return parsed.date()

    @field_validator("appointment_time", mode="before")
    def normalize_time(cls, v):
        parsed = dateparser.parse(v)
        if not parsed:
            raise ValueError("Invalid or unclear time format.")
        return parsed.strftime("%I:%M %p")

    @field_validator("phone")
    def validate_phone(cls, v):
        if v and not PHONE_REGEX.match(v.strip()):
            raise ValueError("Phone must have exactly 10 digits.")
        return v.strip()


# -----------------------------
# LLM CONFIG
# -----------------------------
model = OpenAIChatModel(
    "gpt-5-mini",
    provider=OpenAIProvider(
        api_key= api_key
    )
)

assistant = Agent(
    model=model,
    system_prompt=(
        "You are a friendly and conversational dental assistant. "
        "Ask for **only one piece of information at a time** (e.g., first ask for their name,then email,then date, then time and service)"
        "Never list all questions together. "
        # "Validate date and time"
        "Keep responses short, polite, and natural — like a human conversation. "
        "Once you have all details, call the appropriate tool (verify_slot or register_appointment) yourself. "
        "If the user says 'yes', figure out what they mean based on context."
        "You should not deviate from dental topic and if the user inquire about other stuff except dental booking politely deny the request"
)
)
AVAILABLE_SLOTS = {
    "09:00 AM": "Available",
    "11:00 AM": "Available",
    "2:00 PM": "Unavailable"
}

BOOKINGS: Dict[str, Appointment] = {}

@assistant.tool
def verify_slot(ctx: RunContext[None], appt: Appointment) -> str:
    t = appt.appointment_time
    if not t or t not in AVAILABLE_SLOTS:
        return f"'{t}' is not recognized. Available: {', '.join(AVAILABLE_SLOTS.keys())}"
    return f"{t} is {AVAILABLE_SLOTS[t].lower()}."

@assistant.tool
def register_appointment(ctx: RunContext[None], appt: Appointment):
    key = f"{appt.user_name}_{appt.appointment_date}"
    BOOKINGS[key] = appt
    return {
        "status": "success",
        "confirmation": (
            f"Appointment confirmed for {appt.user_name}\n"
            f"Date: {appt.appointment_date}\n"
            f"Time: {appt.appointment_time}\n"
            f"Service: {appt.service}"
        )
    }

# -----------------------------
# RUNNER
# -----------------------------
async def agent_reply(user_input: str, history):
    result = await assistant.run(user_input, message_history=history)
    return result.output, result.all_messages()