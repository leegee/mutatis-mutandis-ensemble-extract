# tests/test_request_budget.py

import pytest
import time

from langchain_core.messages import HumanMessage

from diachronic_agents.llm.request_budget import (
    GroqRequestBudget,
    GroqTokenBudgetExceeded,
)
from diachronic_agents.llm.request_budget import GroqRequestBudget


def test_estimates_input_and_output_tokens():
    budget = GroqRequestBudget()

    input_tokens, total = budget.estimate_tokens(
        [HumanMessage(content="Find descriptions of white hair.")],
        max_output_tokens=1000,
    )

    assert input_tokens > 0
    assert total == input_tokens + 1000


def test_rejects_request_over_limit():
    budget = GroqRequestBudget(tpm_limit=1000)

    with pytest.raises(GroqTokenBudgetExceeded, match="exceeds"):
        budget.reserve(
            [HumanMessage(content="A short question.")],
            max_output_tokens=1000,
        )


def test_tracks_rolling_token_budget(monkeypatch):
    budget = GroqRequestBudget(
        tpm_limit=2000,
        window_seconds=0.2,
    )

    message = [HumanMessage(content="A short question.")]

    budget.reserve(message, max_output_tokens=1000)

    started = time.monotonic()
    budget.reserve(message, max_output_tokens=1000)
    elapsed = time.monotonic() - started

    assert elapsed >= 0.15
    

def test_allows_requests_within_budget():
    budget = GroqRequestBudget(tpm_limit=5000)

    message = [HumanMessage(content="A short question.")]

    estimate = budget.reserve(
        message,
        max_output_tokens=1000,
    )

    assert estimate < 5000


def test_reserve_waits_for_rolling_window_to_expire(monkeypatch):
    budget = GroqRequestBudget(
        tpm_limit=1000,
        window_seconds=0.2,
    )

    # Keep the test independent of tokenisation and prompt size.
    monkeypatch.setattr(
        budget,
        "estimate_tokens",
        lambda *args, **kwargs: (0, 700),
    )

    # First request reserves 700 tokens.
    budget.reserve([])

    # A second 700-token request cannot fit yet, but should wait
    # until the first reservation expires.
    started = time.monotonic()
    budget.reserve([])
    elapsed = time.monotonic() - started

    assert elapsed >= 0.15
