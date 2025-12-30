**TASK - 1 Description**

Build an interactive text-based agent that helps users book dental appointments using PydanticAI.

Create a conversational AI agent (chat interface) that:

	1.	Asks the user for relevant details to schedule a dental appointment:
	•	Patient name
	•	Type of dental service (e.g., cleaning, filling, root canal, etc.)
	•	Preferred date and time
	•	Contact details
	2.	Confirms the booking details back to the user before finalizing.
	3.	Optionally, handle simple user changes (e.g., “I want to change the time to 4 PM” or “Actually, make it on Friday”).
	4.	Use PydanticAI to:
	•	Define structured data models for the appointment.
	•	Validate inputs and ensure correct types (date/time, contact info, etc.).
	•	Manage the flow of the conversation.

**Step by Step Approach:**

**Setup:** 

    •  Create Python 3.10+ venv and install pydantic, pydantic-ai, huggingface-hub (and fastapi/uvicorn if web UI later).
	•   Choose LLM: pick a conversational HF model and get HF_TOKEN (use Hugging Face Inference API / InferenceClient).
	•	Define schema: write a Pydantic Appointment model (patient_name, service, preferred_date, preferred_time, contact_email/phone, notes).
	•	Validators: add Pydantic validators (date ≥ today, time format, email/phone regex).
	•	Agent flow: design simple stateful flow — greeting → collect fields one-by-one → validate each field → confirm.
	•	Integrate PydanticAI: register the Appointment schema so the agent coerces/validates LLM outputs into typed data.
	•	Prompting: craft a concise system prompt telling the model to fill the schema, ask 1 clarifying question on invalid/ambiguous inputs.
	•	Edit handling: detect edit intents (simple LLM intent prompt or rule) and apply a patch to the current Appointment model.
	•	Confirmation: show a compact summary, ask final confirm (yes/no); on confirm, generate booking id and persist.
	•	Persistence: save booking as JSON or to SQLite; log minimal info and avoid logging full PII in plaintext.
	•	Error & rate handling: handle HF rate limits, retry/backoff, and ask precise follow-ups for parse errors.
	•	Testing: unit tests for validators, convo flow tests (happy path + edit + invalid inputs).
	•	Optional extras: add FastAPI + WebSocket chat UI, send SMS/email on confirmation (Twilio/SendGrid), or integrate real calendar API.
	•	Security: store HF token in env vars, encrypt stored contact info if production.


** To generate token.json for accessing Google Calendar **
run this command: 
cd .\backend\
uv run .\quickstart.py


** To start the backend **
activate .venv and then cd to backend and run the below command
uvicorn main:app --reload --port 8000

** To start the frontend **
activate .venv and then cd to frontend and run the below command
npm start

Note: You may need to run "npm install" the first time before running "npm start". Also run "npm install react-markdown remark-gfm" before npm start so that the markdown dependencies are installed. All these commands need to be run at "cd frontend"


# 🦷 Dental Appointment Booking Assistant  
### React • FastAPI • PydanticAI • Google Calendar • Pinecone • Rate Limiting  

A fully conversational AI-powered dental appointment booking assistant.  
Users interact naturally through a chat-based UI, and the backend handles intelligent reasoning, real-time availability checks, Google Calendar scheduling, persistence, and rate limiting.

---

# 📘 Overview

This project provides an end‑to‑end system for managing dental appointments through natural language:

- A modern **React chat interface**
- A **FastAPI backend** powered by **PydanticAI**
- Automatic **Google Calendar scheduling**
- **Pinecone** as a persistence layer for appointments
- **Rate limiting** for API protection

The user interacts only with the AI assistant — no forms, no buttons.

---

# 🚀 Features

## 🧠 Conversational AI Booking
The assistant:
- Asks one question at a time  
- Validates date, time, phone, and email  
- Detects missing or invalid fields  
- Prevents ambiguous instructions  
- Confirms before scheduling  

Once all details are gathered, the assistant calls backend tools automatically.

---

## 📅 Google Calendar Integration
The backend:
- Checks dentist availability  
- Prevents overlapping bookings  
- Creates real Google Calendar events  
- Stores the `google_event_id` for future management  

Uses OAuth2 with:
- `credentials.json` (OAuth client secrets)  
- `token.json` (auto-generated at first authorization)

---

## 🗄 Pinecone Persistence
Stores:
- User profiles  
- Appointment records  
- Metadata (event IDs, start/end time, reason, etc.)

Appointments can be queried with:
```
GET /appointments?user_id=<email>
```

---

## 🔒 Rate Limiting
To protect the backend, each IP can make:
- **10 requests per minute**

A limit breach returns:
```
HTTP 429 Too Many Requests
```

This applies to all main API endpoints.

---

# 🏗 Architecture

```
User → React Chat UI → FastAPI → PydanticAI Agent → Tools:
    • Google Calendar (availability + event creation)
    • Pinecone (save/read appointments)
```

The LLM orchestrates the entire workflow.

---

# 🗂 Project Structure

```
backend/
  main.py
  app/
    llm/
      agent.py
    google_calendar.py
    persistence.py
    models.py
    rate_limit.py
    pinecone_client.py

frontend/
  src/App.jsx
```

---

# ⚙ Backend Setup (Using uv)

## 1. Install dependencies
From `backend/`:

```
uv sync
```

To add new dependencies:

```
uv add fastapi uvicorn pydantic-ai python-dotenv google-auth google-auth-oauthlib google-api-python-client pinecone-client python-dateutil
```

---

# 🔧 Environment Variables

Create `backend/.env`:

```
OPENROUTER_API_KEY=sk-xxxx
PINECONE_API_KEY=xxxx
PINECONE_INDEX_NAME=dental-appointments
GOOGLE_CALENDAR_ID=primary
```

---

# 🔐 Google Calendar Setup

1. Go to **Google Cloud Console → APIs & Services → Credentials**
2. Create an **OAuth Client ID**
3. Download **credentials.json**
4. Place it inside `backend/`
5. When the backend first needs calendar access, your browser will open for OAuth
6. A **token.json** file will be generated automatically

Requires enabling:
- Google Calendar API

---

# 📦 Pinecone Setup

1. Create a serverless index:
   - Name: `dental-appointments`
   - Dimension: 64
   - Metric: cosine  
2. Confirm `PINECONE_API_KEY` is valid  

Backend loads the index in `pinecone_client.py`.

---

# 🚀 Running the Backend

```
uv run uvicorn main:app --reload
```

Open API docs:

```
http://localhost:8000/docs
```

---

# 💻 Frontend Setup

```
cd frontend
npm install
npm start
```

Open:
```
http://localhost:3000
```

---

# 🧪 Testing Guide

## ✔ Full Booking Flow
1. Open UI  
2. Type:  
   ```
   I want to book an appointment
   ```  
3. Provide all details as the assistant asks  
4. A Google Calendar event is created  
5. Appointment appears in Pinecone:
   ```
   GET /appointments?user_id=<email>
   ```

---

## ✔ Slot Conflict Handling
Try to book the same slot again.  
Expected response:
```
That time slot is already booked.
```

---

## ✔ Rate Limiting
Send >10 requests within 60 seconds.  
Response:
```
HTTP 429 Too Many Requests
```

---

# 🧰 API Summary

### POST /chat
```
{ "message": "Hello" }
```

### POST /appointments  
### GET /appointments?user_id=<email>  
### POST /book  
### POST /check_slot  
### POST /reset  

---

# 🧯 Troubleshooting

### Google OAuth “App Not Verified”
Add your email to OAuth test users  
or publish the OAuth app publicly.

### Pinecone vector errors
Ensure vectors are non‑zero and match index dimensions.

### Chat endpoint hangs
Use synchronous `agent.run_sync()` instead of thread wrappers.

---


# 🗂️ User Information Storage & Personalization

## 🎯 Objective
Enable the Dental Appointment Agent to maintain memory of user-specific details so the conversation becomes more natural, consistent, and personalized across sessions.

## 🔧 Features Added This Week
1. Persistent user profile storage  
2. Preference-based personalization  
3. Appointment history recall  
4. Context-aware dialogue generation  
5. Safety boundaries for stored memory  
6. Memory backend integration (Pinecone or relational DB)

---

## 🧠 What the Agent Should Remember

### ✔️ User Profile Details
- Name  
- Phone  
- Email  
- Insurance provider (if voluntarily shared)  
- Preferred dentist  
- Preferred appointment times (e.g., “evenings”, “weekends”)  
- Dental anxiety or sedation preference (only if explicitly provided)  
- Last checkup date (when relevant)

### ✔️ Long-Term Conversation Context
- Previous visits  
- Pending appointments  
- Cancellations  
- Frequently requested services  
- Preference for short vs. detailed replies  

### ✔️ Personalization Cues
- Likes brief responses  
- Prefers step-by-step explanations  
- Emoji preference  
- Tone preference (formal or friendly)

---

## 🚫 Safety: What the Agent Should *Not* Remember

To maintain user trust and comply with safety standards:
- Medical history  
- Dental conditions or diagnoses  
- Sensitive personal attributes (religion, politics, etc.)  
- Payment / credit card information  
- Minors’ data without safeguards  

---
