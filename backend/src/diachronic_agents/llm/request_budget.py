
from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from typing import Any, Sequence

import tiktoken

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool


INVESTIGATOR_MAX_OUTPUT_TOKENS = 2048 #  1024

GROQ_TPM_LIMIT = 8000

# Leave some room for tokenisation differences and API overhead.
GROQ_TPM_SAFETY_LIMIT = 7600

WINDOW_SECONDS = 60
ESTIMATE_MARGIN = 1.20


class GroqTokenBudgetExceeded(RuntimeError):
    pass


class GroqRequestBudget:
    """Conservative preflight and rolling token budget for Groq requests."""

    def __init__(
        self,
        *,
        tpm_limit: int = GROQ_TPM_SAFETY_LIMIT,
        window_seconds: int = WINDOW_SECONDS,
    ):
        self.tpm_limit = tpm_limit
        self.window_seconds = window_seconds
        self.encoding = tiktoken.get_encoding("o200k_base")

        self._reservations: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def estimate_tokens(
        self,
        messages: Sequence[BaseMessage],
        *,
        tools: Sequence[BaseTool] = (),
        max_output_tokens: int = INVESTIGATOR_MAX_OUTPUT_TOKENS,
    ) -> tuple[int, int]:
        """Estimate input and total request tokens.

        Includes message contents, message metadata, tool schemas,
        and the maximum permitted completion.
        """

        message_payload = [
            message.model_dump(exclude_none=True)
            for message in messages
        ]

        tool_payload = [
            convert_to_openai_tool(tool)
            for tool in tools
        ]

        message_json = json.dumps(
            message_payload,
            ensure_ascii=False,
            default=str,
        )

        tool_json = json.dumps(
            tool_payload,
            ensure_ascii=False,
            default=str,
        )

        message_tokens = len(
            self.encoding.encode(message_json)
        )

        tool_tokens = len(
            self.encoding.encode(tool_json)
        )

        raw_input_tokens = message_tokens + tool_tokens

        print(
            "Investigator request estimate: "
            f"messages={message_tokens}, "
            f"tools={tool_tokens}, "
            f"combined={raw_input_tokens}"
        )

        estimated_input_tokens = math.ceil(
            raw_input_tokens * ESTIMATE_MARGIN
        )

        total = estimated_input_tokens + max_output_tokens

        return estimated_input_tokens, total

    def reserve(
        self,
        messages: Sequence[BaseMessage],
        *,
        tools: Sequence[BaseTool] = (),
        max_output_tokens: int = INVESTIGATOR_MAX_OUTPUT_TOKENS,
    ) -> int:
        """Check and reserve estimated tokens, waiting for rolling capacity."""

        input_tokens, estimated_total = self.estimate_tokens(
            messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
        )

        # A request that cannot fit even into an empty window cannot be
        # resolved by waiting.
        if estimated_total > self.tpm_limit:
            raise GroqTokenBudgetExceeded(
                "Investigator request exceeds the safe request budget: "
                f"estimated input={input_tokens}, "
                f"maximum output={max_output_tokens}, "
                f"total={estimated_total}, "
                f"limit={self.tpm_limit}. "
                "Reduce conversation context or output allowance."
            )

        while True:
            wait_seconds = 0.0

            with self._lock:
                now = time.monotonic()
                cutoff = now - self.window_seconds

                # Remove reservations that have expired.
                while (
                    self._reservations
                    and self._reservations[0][0] <= cutoff
                ):
                    self._reservations.popleft()

                used = sum(
                    tokens
                    for _, tokens in self._reservations
                )

                if used + estimated_total <= self.tpm_limit:
                    self._reservations.append((now, estimated_total))
                    return estimated_total

                # Determine how long we must wait for enough old
                # reservations to expire.
                required_to_expire = (
                    used + estimated_total - self.tpm_limit
                )

                freed_tokens = 0
                wait_until = now

                for timestamp, tokens in self._reservations:
                    freed_tokens += tokens
                    wait_until = timestamp + self.window_seconds

                    if freed_tokens >= required_to_expire:
                        break

                wait_seconds = max(0.0, wait_until - now) + 0.05

            # Sleep outside the lock so other requests can proceed.
            print(
                "Investigator token budget full: "
                f"reserved={used}, "
                f"requested={estimated_total}, "
                f"limit={self.tpm_limit}. "
                f"Waiting {wait_seconds:.1f} seconds."
            )

            time.sleep(wait_seconds)


investigator_request_budget = GroqRequestBudget()
