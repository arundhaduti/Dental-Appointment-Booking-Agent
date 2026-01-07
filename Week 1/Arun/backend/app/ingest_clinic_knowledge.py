# ingest_clinic_knowledge.py

import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

from pinecone_client import clinic_index

# -------------------------------------------------
# Setup
# -------------------------------------------------

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not set")

OPENROUTER_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
EMBEDDING_MODEL = "openai/text-embedding-3-small"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
}

# -------------------------------------------------
# Embedding helper (OpenRouter)
# -------------------------------------------------

def embed(text: str) -> List[float]:
    response = requests.post(
        OPENROUTER_EMBEDDING_URL,
        headers=HEADERS,
        json={
            "model": EMBEDDING_MODEL,
            "input": text,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Embedding failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    return data["data"][0]["embedding"]

# -------------------------------------------------
# Clinic knowledge documents
# -------------------------------------------------

CLINIC_DOCS: List[Dict] = [
    {
        "id": "cleaning_pricing",
        "text": "Teeth cleaning at our clinic costs between ₹800 and ₹1,200 and typically takes 30 to 45 minutes.",
        "metadata": {
            "type": "clinic_info",
            "category": "pricing",
            "service": "cleaning",
            "source": "clinic_internal"
        }
    },
    {
        "id": "clinic_hours",
        "text": (
            "The clinic operates Monday to Saturday from 9:00 AM to 1:00 PM "
            "and from 2:00 PM to 6:00 PM. The clinic is closed on Sundays."
        ),
        "metadata": {
            "type": "clinic_info",
            "category": "hours",
            "source": "clinic_internal"
        }
    },
    {
        "id": "cancellation_policy",
        "text": (
            "Appointments can be cancelled free of charge up to 24 hours before "
            "the scheduled time. Late cancellations may incur a ₹500 fee."
        ),
        "metadata": {
            "type": "clinic_info",
            "category": "policy",
            "source": "clinic_internal"
        }
    },
    {
        "id": "doctor_ramesh",
        "text": (
            "Dr. Ramesh is a senior dentist at the clinic and speaks English and Kannada."
        ),
        "metadata": {
            "type": "clinic_info",
            "category": "doctor",
            "source": "clinic_internal"
        }
    },
]

# -------------------------------------------------
# Ingestion logic
# -------------------------------------------------

def ingest_clinic_docs(docs: List[Dict]) -> None:
    vectors = []

    for doc in docs:
        text = doc["text"].strip()
        if not text:
            continue

        embedding = embed(text)

        vectors.append({
            "id": doc["id"],
            "values": embedding,
            "metadata": {
                **doc["metadata"],
                "text": text
            }
        })

    if not vectors:
        print("❌ No clinic documents to ingest.")
        return

    clinic_index.upsert(
        vectors=vectors,
        namespace="clinic"
    )

    print(f"✅ Ingested {len(vectors)} clinic knowledge chunks.")

# -------------------------------------------------
# Run
# -------------------------------------------------

if __name__ == "__main__":
    ingest_clinic_docs(CLINIC_DOCS)
