# ingest_general_dental_knowledge.py

import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

from pinecone_client import general_index

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
# External dental knowledge documents
# -------------------------------------------------

GENERAL_DENTAL_DOCS: List[Dict] = [
    {
        "id": "what_is_teeth_cleaning",
        "text": (
            "Teeth cleaning is a professional dental procedure that removes plaque, "
            "tartar, and stains from teeth to help prevent cavities and gum disease."
        ),
        "metadata": {
            "type": "educational",
            "topic": "cleaning",
            "source": "trusted_public"
        }
    },
    {
        "id": "how_often_cleaning",
        "text": (
            "Most dentists recommend having a professional teeth cleaning every six months, "
            "although some people may need more frequent cleanings."
        ),
        "metadata": {
            "type": "educational",
            "topic": "cleaning",
            "source": "trusted_public"
        }
    },
    {
        "id": "xray_safety",
        "text": (
            "Dental X-rays are generally considered safe and use very low levels of radiation. "
            "They help dentists detect problems that may not be visible during a regular exam."
        ),
        "metadata": {
            "type": "educational",
            "topic": "xray",
            "source": "trusted_public"
        }
    },
    {
        "id": "what_is_plaque",
        "text": (
            "Plaque is a sticky film of bacteria that forms on teeth. If not removed regularly, "
            "it can lead to tooth decay and gum disease."
        ),
        "metadata": {
            "type": "educational",
            "topic": "plaque",
            "source": "trusted_public"
        }
    },
]

# -------------------------------------------------
# Ingestion logic
# -------------------------------------------------

def ingest_general_docs(docs: List[Dict]) -> None:
    vectors = []

    for doc in docs:
        text = doc["text"].strip()
        if not text:
            continue

        # Safety check: no prices allowed in general knowledge
        if "₹" in text:
            raise ValueError(
                f"❌ Price detected in general dental knowledge doc: {doc['id']}"
            )

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
        print("❌ No general dental documents to ingest.")
        return

    general_index.upsert(
        vectors=vectors,
        namespace="general"
    )

    print(f"✅ Ingested {len(vectors)} general dental knowledge chunks.")

# -------------------------------------------------
# Run
# -------------------------------------------------

if __name__ == "__main__":
    ingest_general_docs(GENERAL_DENTAL_DOCS)
