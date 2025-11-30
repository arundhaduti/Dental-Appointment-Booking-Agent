from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio

from agent import agent_reply

app = FastAPI()

# Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conversation memory
history = []

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(req: ChatRequest):
    global history
    response, history = await agent_reply(req.message, history)
    return {"reply": response}

@app.post("/reset")
async def reset_chat():
    global history
    history = []
    return {"status": "reset"}

