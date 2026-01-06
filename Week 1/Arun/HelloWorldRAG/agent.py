from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic import BaseModel
from dotenv import load_dotenv
import os

# Knowledge base
KNOWLEDGE_BASE = [
    "PydanticAI is a framework for building type-safe AI agents in Python.",
    "RAG stands for Retrieval-Augmented Generation.",
    "RAG improves accuracy by injecting external context into prompts.",
]


STOPWORDS = {"is", "what", "the", "a", "an", "for", "in", "of", "by"}

def tokenize(text: str) -> set[str]:
    return {
        w for w in text.lower().replace("?", "").split()
        if w not in STOPWORDS
    }

def retrieve(query: str) -> str:
    query_tokens = tokenize(query)

    best_doc = None
    best_score = -1
    best_length = -1

    for doc in KNOWLEDGE_BASE:
        doc_tokens = tokenize(doc)
        overlap = query_tokens & doc_tokens
        score = len(overlap)

        if (
            score > best_score
            or (score == best_score and len(doc_tokens) > best_length)
        ):
            best_score = score
            best_length = len(doc_tokens)
            best_doc = doc

    if best_score <= 0:
        return "No relevant information found."

    return best_doc







# Output schema
class Answer(BaseModel):
    response: str


# Agent
load_dotenv()

openrouter_provider = OpenAIProvider(base_url="https://openrouter.ai/api/v1",api_key=os.getenv("OPENROUTER_API_KEY"))

model = OpenAIChatModel('kwaipilot/kat-coder-pro:free',provider=openrouter_provider)

agent = Agent(
    model=model,
    output_type=Answer,
    system_prompt="""
You are a helpful assistant.
Answer ONLY using the provided context.
If the context is insufficient, say so clearly.
"""
)

# Inject retrieved context into the prompt
def ask_with_rag(question: str) -> Answer:
    context = retrieve(question)
    print("***** Context injected into prompt:", context)

    prompt = f"""
Context:
{context}

Question:
{question}
"""

    return agent.run_sync(prompt)

# Run
result = ask_with_rag("What is RAG?")
print("Result:", result.output.response)
