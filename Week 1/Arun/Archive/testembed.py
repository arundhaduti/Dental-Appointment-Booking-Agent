from typing import List, Dict
import os
import requests
from typing import List, Dict
from dotenv import load_dotenv



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

emb = embed("test")
print(emb)  # must be 1536


