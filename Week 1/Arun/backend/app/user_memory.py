from datetime import datetime
from typing import Optional

from app.pinecone_client import index
from app.models import UserMemory

# Same dummy-vector strategy used elsewhere
DUMMY_VECTOR = [1.0] + [0.0] * 63


def save_user_memory(memory: UserMemory) -> None:
    """
    Upserts user memory into Pinecone.

    This overwrites existing memory for the same user_id.
    """
    index.upsert(
        vectors=[
            (
                f"user-memory-{memory.user_id}",
                DUMMY_VECTOR,
                {
                    "type": "user_memory",
                    "user_id": memory.user_id,
                    **memory.model_dump(exclude={"last_updated"}),
                    "last_updated": memory.last_updated.isoformat(),
                },
            )
        ],
        namespace="user_memory",
    )


def get_user_memory(user_id: str) -> Optional[UserMemory]:
    """
    Fetch stored user memory for personalization.
    """
    res = index.query(
        namespace="user_memory",
        vector=DUMMY_VECTOR,
        top_k=1,
        filter={"user_id": {"$eq": user_id}},
        include_metadata=True,
    )

    matches = res.get("matches") or []
    if not matches:
        return None

    md = matches[0]["metadata"]

    return UserMemory(
        user_id=md["user_id"],
        name=md.get("name"),
        phone=md.get("phone"),
        preferred_times=md.get("preferred_times", []),
        preferred_dentist=md.get("preferred_dentist"),
        insurance_provider=md.get("insurance_provider"),
        dental_anxiety=md.get("dental_anxiety"),
        prefers_brief_responses=md.get("prefers_brief_responses"),
        prefers_emojis=md.get("prefers_emojis"),
        tone=md.get("tone"),
        last_updated=datetime.fromisoformat(md["last_updated"]),
    )
