"""
API tests with a fake service: no LanceDB, Postgres or model needed.

TestClient is used WITHOUT a `with` block so the lifespan (which builds the
real service) does not run; get_service is overridden instead.

    pip install pytest httpx
    pytest tests
"""

import pytest
from fastapi.testclient import TestClient

from mutatis_mutandis.api import app, get_service
from mutatis_mutandis.core import VectorNotFoundError
from mutatis_mutandis.service import SearchOutcome

PID = "ef2f4aaf68dc6c924a2f1218e470a555060be2cb886a0ef1ebf169b800508f8a"


def _hit(rank=1):
    return {
        "rank": rank, "passage_id": PID, "corpus": "misc", "doc_id": "d1",
        "pub_year": 1972, "distance": 0.12, "score": None, "sim_q": None,
        "sim_neg": None, "word_start": 0, "word_end": 40,
        "token_start": 260, "token_end": 300, "title": "Albinism",
        "author": "Psaila", "filepath": "misc/x.xml", "text": "her hair is whitish",
        "match_start": None, "match_end": None,
    }


def _text_hit(rank=1):
    h = _hit(rank)
    h["distance"] = 0.0
    h["match_start"] = 270
    h["match_end"] = 272
    h["text"] = "her hair is whitish and pale"
    return h


class FakeService:
    def __init__(self):
        self.last = None
        self.last_text = None

    def search(self, params):
        self.last = params
        if params.vector_id and params.vector_id.startswith("00"):
            raise VectorNotFoundError("no such passage")
        return SearchOutcome(results=[_hit()], warnings=["note"])

    def text_search(self, params):
        self.last_text = params
        return SearchOutcome(results=[_text_hit()], warnings=[])


@pytest.fixture
def client():
    fake = FakeService()
    app.dependency_overrides[get_service] = lambda: fake
    c = TestClient(app)
    c.fake = fake
    yield c
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_search_by_text(client):
    r = client.post("/search", json={"query": "white hair", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1 and body["warnings"] == ["note"]
    assert body["results"][0]["passage_id"] == PID
    assert client.fake.last.limit == 5


def test_requires_exactly_one_query_source(client):
    assert client.post("/search", json={}).status_code == 422
    both = {"query": "x", "vector_id": PID}
    assert client.post("/search", json=both).status_code == 422


def test_bad_passage_id_rejected(client):
    r = client.post("/search", json={"vector_id": "not-a-hash"})
    assert r.status_code == 422


def test_unknown_vector_is_404(client):
    r = client.post("/search", json={"vector_id": "00" + PID[2:]})
    assert r.status_code == 404


def test_year_order_validated(client):
    r = client.post("/search", json={"query": "x", "start_year": 1700, "end_year": 1600})
    assert r.status_code == 422


def test_text_search(client):
    r = client.post("/text-search", json={"query": "white hair", "limit": 10, "window_tokens": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["results"][0]["match_start"] == 270
    assert client.fake.last_text.query == "white hair"
    assert client.fake.last_text.window_tokens == 30


def test_text_search_requires_query(client):
    assert client.post("/text-search", json={}).status_code == 422


def test_text_search_year_order(client):
    r = client.post(
        "/text-search",
        json={"query": "x", "start_year": 1800, "end_year": 1700},
    )
    assert r.status_code == 422
