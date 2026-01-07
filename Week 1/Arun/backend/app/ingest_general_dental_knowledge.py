# ingest_general_dental_knowledge.py

import os
from dotenv import load_dotenv
from typing import List, Dict

from openai import OpenAI
from pinecone_client import general_index  # separate index object

# -------------------------------------------------
# Setup
# -------------------------------------------------

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

EMBEDDING_MODEL = "text-embedding-3-small"

# -------------------------------------------------
# Embedding helper
# -------------------------------------------------

def embed(text: str) -> List[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


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

        # Safety check: no prices allowed here
        if "₹" in text:
            raise ValueError(
                f"❌ Price detected in general knowledge doc: {doc['id']}"
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
