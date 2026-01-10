# create_rag_indexes.py

import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENVIRONMENT")  # e.g. "gcp-starter"

pc = Pinecone(api_key=PINECONE_API_KEY)

# ⚠️ MUST MATCH embedding model dimension
EMBEDDING_DIMENSION = 1536  # for text-embedding-3-small

def create_index_if_not_exists(index_name: str):
    existing = [i["name"] for i in pc.list_indexes()]

    if index_name in existing:
        print(f"✅ Index '{index_name}' already exists.")
        return

    pc.create_index(
        name=index_name,
        dimension=EMBEDDING_DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"  # or your Pinecone region
        )
    )

    print(f"🚀 Created index '{index_name}'")

if __name__ == "__main__":
    create_index_if_not_exists("clinic-knowledge")
    create_index_if_not_exists("dental-knowledge")
