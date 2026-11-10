import os

from langchain_groq import ChatGroq

from diachronic_agents.llm.request_budget import (
    INVESTIGATOR_MAX_OUTPUT_TOKENS,
)

def create_llm(
    model: str = "openai/gpt-oss-20b", 
    *, 
    max_tokens: int = INVESTIGATOR_MAX_OUTPUT_TOKENS,
    model_kwargs = None
):
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    return ChatGroq(
        model            = model,
        max_tokens       = max_tokens,
        reasoning_effort = "medium",
        temperature      = 0,
        max_retries      = 2,
    )
    