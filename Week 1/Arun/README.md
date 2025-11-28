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



** To start the backend **
activate .venv and then cd to backend and run the below command
uvicorn main:app --reload --port 8000

** To start the frontend **
activate .venv and then cd to frontend and run the below command
npm start

Note: You may need to run "npm install" the first time before running "npm start". Also run "npm install react-markdown remark-gfm" before npm start so that the markdown dependencies are installed. All these commands need to be run at "cd frontend"