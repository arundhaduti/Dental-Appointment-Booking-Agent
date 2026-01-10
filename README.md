# 🦷 Dental Appointment Booking Assistant

A full-stack, production-grade AI agent that books real dental appointments using natural language.

---

## Overview
This project implements a conversational dental appointment booking system powered by **PydanticAI**, **FastAPI**, **Google Calendar**, and **Pinecone**. Users talk to the assistant through a React UI, and the agent handles validation, scheduling, memory, and retrieval.

---

## Core Features
- Natural language appointment booking
- Date, time, phone and email validation
- Google Calendar availability + booking
- Pinecone-based appointment storage
- Long-term user memory & personalization
- Retrieval-Augmented Generation (Clinic + Dental knowledge)
- Rate limiting and security

---

## Architecture
User → React UI → FastAPI → PydanticAI → Google Calendar & Pinecone

---

## Project Structure
backend/
  main.py
  app/
    llm/agent.py
    google_calendar.py
    persistence.py
    models.py
    rate_limit.py
    pinecone_client.py

frontend/
  src/App.jsx

---

## Environment Variables
Create backend/.env

OPENROUTER_API_KEY=
PINECONE_API_KEY=
PINECONE_INDEX_NAME=dental-appointments
GOOGLE_CALENDAR_ID=primary

---

## Google Calendar Setup
1. Create OAuth client
2. Download credentials.json
3. Place inside backend/
4. Run quickstart.py to generate token.json

---

## Pinecone Setup
Create index:
- Name: dental-appointments
- Dimension: 64
- Metric: cosine

---

## Running Backend
cd backend
uv run uvicorn main:app --reload --port 8000

---

## Running Frontend
cd frontend
npm install
npm install react-markdown remark-gfm
npm start

---

## RAG
Two Pinecone indexes:
- Clinic Knowledge
- General Dental Knowledge
Run create_rag_indexes.py to create these 2 in pinecone

Run ingestion scripts when documents change.

---

## User Memory
Stored:
- Name
- Email
- Phone
- Preferences
- Appointment history

Not stored:
- Medical diagnosis
- Payment data
- Sensitive attributes

---

## API
POST /chat
POST /book
POST /check_slot
GET /appointments?user_id=email

---

## Rate Limiting
10 requests per minute per IP

---

## Testing
Try:
“I want to book a dental appointment”
Provide details and confirm

---

## Troubleshooting
Google OAuth errors → add test user
Pinecone errors → verify dimension and API key
