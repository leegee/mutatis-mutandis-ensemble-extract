"""
forward_search.py - Forward diachronic search.

Shared retrieval mechanics are implemented in base_search.py.
"""

from typing import Any, TypedDict

from diachronic_agents.workflows.base_search import (
    SearchState,
    SearchTask,
    build_search_workflow,
)
from diachronic_agents.retrieval.passage_retriever import PassageRetriever


class ForwardSearchTask(SearchTask):
    """Task dispatched for one forward seed."""


class ForwardSearchState(SearchState):
    """State for forward diachronic retrieval."""


def build_forward_search_workflow(
    retriever: PassageRetriever | None = None,
    *,
    checkpointer=None,
):
    """Build the forward diachronic search workflow."""

    return build_search_workflow(
        direction="forward",
        retriever=retriever,
        checkpointer=checkpointer,
    )

