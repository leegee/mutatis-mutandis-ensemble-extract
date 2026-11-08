from langchain_groq import ChatGroq

from diachronic_agents.llm.request_budget import (
    INVESTIGATOR_MAX_OUTPUT_TOKENS,
)

def create_grok_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0,
        max_retries=2,
        max_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
        reasoning_effort="low",
    )
