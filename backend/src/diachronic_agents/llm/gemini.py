from langchain_google_genai import ChatGoogleGenerativeAI

from diachronic_agents.llm.request_budget import (
    INVESTIGATOR_MAX_OUTPUT_TOKENS,
)

def create_gemini_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-3.8-flash",
        temperature=0,
        max_retries=2,
        max_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
        # reasoning_effort="low",
    )