# tests/test_passage_retriever.py


from __future__ import annotations

from types import SimpleNamespace

from diachronic_agents.retrieval.passage_retriever import (
    PassageRetriever,
)


class FakeService:
    def __init__(self):
        self.search_params = None
        self.text_search_params = None
        self.inspected = None

    def search(self, params):
        self.search_params = params
        return SimpleNamespace(
            results=[semantic_hit()],
            warnings=["A test warning"],
        )

    def text_search(self, params):
        self.text_search_params = params
        return SimpleNamespace(
            results=[lexical_hit()],
            warnings=[],
        )

    def inspect_passage(self, passage_id, *, representation):
        self.inspected = {
            "passage_id": passage_id,
            "representation": representation,
        }
        return {
            "passage_id": passage_id,
            "text": "Inspected passage text.",
            "title": "Test document",
        }


def semantic_hit():
    return {
        "passage_id": "passage-1",
        "corpus": "eebo",
        "doc_id": "doc-1",
        "pub_year": 1650,
        "scale": "broad",
        "rank": 1,
        "distance": 0.123,
        "score": 0.877,
        "sim_q": 0.91,
        "sim_neg": 0.22,
        "title": "A Test Document",
        "author": "Test Author",
        "text": "A passage about white hair.",
        "char_start": 100,
        "char_end": 200,
        "word_start": 10,
        "word_end": 30,
        "token_start": 15,
        "token_end": 35,
        "filepath": "eebo/test.txt",
    }


def lexical_hit():
    return {
        "passage_id": "lexical-1",
        "corpus": "eebo",
        "doc_id": "doc-2",
        "pub_year": 1652,
        "rank": 1,
        "distance": 0.0,
        "score": None,
        "sim_q": None,
        "sim_neg": None,
        "title": "Another Document",
        "author": "Another Author",
        "text": "His hair was white.",
        "word_start": 20,
        "word_end": 24,
        "token_start": 25,
        "token_end": 29,
        "match_start": 26,
        "match_end": 28,
        "filepath": "eebo/another.txt",
    }


def test_search_text_forwards_parameters_and_serialises_results():
    service = FakeService()
    retriever = PassageRetriever(service=service)

    result = retriever.search_text(
        "white hair",
        representation="l8",
        start_year=1500,
        end_year=1700,
        limit=7,
        scale="broad",
        include_text=False,
    )

    params = service.search_params

    assert params.query == "white hair"
    assert params.vector_id is None
    assert params.representation == "l8"
    assert params.start_year == 1500
    assert params.end_year == 1700
    assert params.limit == 7
    assert params.scale == "broad"
    assert params.include_text is False

    assert result["warnings"] == ["A test warning"]
    assert len(result["results"]) == 1

    hit = result["results"][0]

    assert hit["passage_id"] == "passage-1"
    assert hit["pub_year"] == 1650
    assert hit["distance"] == 0.123
    assert hit["score"] == 0.877
    assert hit["sim_q"] == 0.91
    assert hit["sim_neg"] == 0.22
    assert hit["text"] == "A passage about white hair."


def test_search_from_passage_uses_vector_id():
    service = FakeService()
    retriever = PassageRetriever(service=service)

    retriever.search_from_passage(
        "passage-seed",
        representation="l8",
        start_year=1500,
        end_year=1800,
        limit=5,
        scale="medium",
    )

    params = service.search_params

    assert params.query is None
    assert params.vector_id == "passage-seed"
    assert params.representation == "l8"
    assert params.start_year == 1500
    assert params.end_year == 1800
    assert params.limit == 5
    assert params.scale == "medium"


def test_search_lexical_forwards_parameters_and_preserves_match_offsets():
    service = FakeService()
    retriever = PassageRetriever(service=service)

    result = retriever.search_lexical(
        "white hair",
        start_year=1600,
        end_year=1700,
        limit=12,
        window_tokens=50,
    )

    params = service.text_search_params

    assert params.query == "white hair"
    assert params.start_year == 1600
    assert params.end_year == 1700
    assert params.limit == 12
    assert params.window_tokens == 50

    assert result["warnings"] == []
    assert len(result["results"]) == 1

    hit = result["results"][0]

    assert hit["passage_id"] == "lexical-1"
    assert hit["distance"] == 0.0
    assert hit["sim_q"] is None
    assert hit["sim_neg"] is None
    assert hit["match_start"] == 26
    assert hit["match_end"] == 28
    assert hit["text"] == "His hair was white."


def inspect_passage(
    self,
    passage_id,
    representation="l8",
    max_chars=1200,
):
    self.calls.append((
        "inspect_passage",
        passage_id,
        representation,
        max_chars,
    ))
    return {"passage_id": passage_id, "text": "Example"}

    
def test_serialisation_handles_missing_optional_fields():
    service = FakeService()
    retriever = PassageRetriever(service=service)

    service.search = lambda params: SimpleNamespace(
        results=[{
            "passage_id": "minimal-1",
        }],
        warnings=[],
    )

    result = retriever.search_text(
        "white hair",
        start_year=1500,
        end_year=1700,
    )

    hit = result["results"][0]

    assert hit["passage_id"] == "minimal-1"
    assert hit["pub_year"] is None
    assert hit["distance"] is None
    assert hit["score"] is None
    assert hit["sim_q"] is None
    assert hit["sim_neg"] is None
    assert hit["match_start"] is None
    assert hit["match_end"] is None

