# backend/app/pinecone_client.py

import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise RuntimeError("ERROR: PINECONE_API_KEY is missing.")

pc = Pinecone(api_key=PINECONE_API_KEY)

# -------------------------------------------------
# Index configs
# -------------------------------------------------

APPOINTMENT_INDEX = "dental-appointments"
CLINIC_KNOWLEDGE_INDEX = "clinic-knowledge"
GENERAL_KNOWLEDGE_INDEX = "dental-knowledge"

APPOINTMENT_DIM = 64          # dummy vectors
EMBEDDING_DIM = 1536          # text-embedding-3-small

SPEC = ServerlessSpec(
    cloud="aws",
    region="us-east-1"
)

# -------------------------------------------------
# Helper: create index if missing
# -------------------------------------------------

def ensure_index(name: str, dimension: int):
    if name in pc.list_indexes().names():
        return

    pc.create_index(
        name=name,
        dimension=dimension,
        metric="cosine",
        spec=SPEC,
    )

# -------------------------------------------------
# Ensure all indexes exist
# -------------------------------------------------

ensure_index(APPOINTMENT_INDEX, APPOINTMENT_DIM)
ensure_index(CLINIC_KNOWLEDGE_INDEX, EMBEDDING_DIM)
ensure_index(GENERAL_KNOWLEDGE_INDEX, EMBEDDING_DIM)

# -------------------------------------------------
# Export index handles
# -------------------------------------------------

index = pc.Index(APPOINTMENT_INDEX)          # appointments + users
clinic_index = pc.Index(CLINIC_KNOWLEDGE_INDEX)
general_index = pc.Index(GENERAL_KNOWLEDGE_INDEX)
