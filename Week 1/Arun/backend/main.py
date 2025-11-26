from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import asyncio

# Import your Week1 agent and tools
from agent import (
    agent,
    Appointment,
    dental_booking_agent,
    check_appointment_slot_available,
    appointmentDetails,
)

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
    message: str  # ⬅️ ONLY the current user message

# 🔥 Global history, same idea as your CLI `msg_history`
msg_history: List[Any] = []

@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Mirror CLI logic:

    msg_history.append({"role": "user", "content": query})
    result = agent.run_sync(query, message_history=msg_history)
    msg_history = result.all_messages()
    """
    global msg_history
    try:
        # 1) Append user message to history
        msg_history.append({"role": "user", "content": req.message})

        # 2) Call the agent in a background thread
        result = await asyncio.to_thread(
            agent.run_sync,
            req.message,
            message_history=msg_history,
        )

        # 3) Replace history with full internal messages from agent
        msg_history = result.all_messages()

        # 4) Return just the reply text to the UI
        return {"reply": result.output}
    except Exception as e:
        return {"error": str(e)}

# ---------- Booking endpoints stay as-is ----------

class BookingRequest(BaseModel):
    name: str
    preferred_date: str  # DD-MM-YYYY
    time: str
    reason: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

@app.post("/book")
async def book(b: BookingRequest):
    """Directly call the dental_booking_agent tool with validated booking data."""
    try:
        appointment = Appointment(
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

@app.post("/check_slot")
async def check_slot(b: BookingRequest):
    """Check availability for the requested time slot using the agent's plain tool."""
    try:
        appointment = Appointment(
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
        status = check_appointment_slot_available(appointment)
        return {"success": True, "status": status}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/appointment")
async def get_latest_appointment():
    """Return the last booked appointment details (in-memory). Useful for demo/testing."""
    return {"appointmentDetails": appointmentDetails}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
