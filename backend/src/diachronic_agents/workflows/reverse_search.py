"""
reverse_search.py - Reverse diachronic search.

Shared retrieval mechanics are implemented in base_search.py.
"""

from diachronic_agents.workflows.base_search import (
    SearchState,
    SearchTask,
    build_search_workflow,
)
from diachronic_agents.retrieval.passage_retriever import PassageRetriever


def build_reverse_search_workflow(
    retriever: PassageRetriever | None = None,
    *,
    checkpointer=None,
):
    """Build the reverse diachronic search workflow."""

    return build_search_workflow(
        direction="reverse",
        retriever=retriever,
        checkpointer=checkpointer,
    )

