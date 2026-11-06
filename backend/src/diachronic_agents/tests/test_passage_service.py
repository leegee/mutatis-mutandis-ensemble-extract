# tests/test_passage_service.py


from __future__ import annotations

from contextlib import contextmanager

import mutatis_mutandis.service as service_module


def make_service():
    """Create a service instance without running its normal initialisation."""
    service = object.__new__(service_module.PassageSearchService)
    service._db = object()
    service.application_name = "test-investigator"
    return service


def test_inspect_passage_loads_record_and_fetches_text(monkeypatch):
    passage_id = "passage-1"
    representation = "l8"

    record = {
        "passage_id": passage_id,
        "corpus": "eebo",
        "doc_id": "doc-1",
        "pub_year": 1650,
        "scale": "broad",
        "char_start": 100,
        "char_end": 200,
        "table": "passage_l8__model__1600_1699",
        "text_length": 25,
        "text_truncated": False,
        "text_window_start": 0,
        "text_window_end": 25,        
    }

    metadata = {
        "title": "A Test Document",
        "author": "Test Author",
        "filepath": "eebo/test.txt",
        "passage_text": "This is the passage text.",
    }

    fake_connection = object()
    calls = {}

    def fake_load_passage_record(db, requested_id, requested_representation):
        calls["load"] = {
            "db": db,
            "passage_id": requested_id,
            "representation": requested_representation,
        }
        return record

    @contextmanager
    def fake_get_connection(*, application_name):
        calls["application_name"] = application_name
        yield fake_connection

    def fake_fetch_passage_texts(conn, records):
        calls["fetch"] = {
            "connection": conn,
            "records": records,
        }
        return [metadata]
        
    monkeypatch.setattr(
        service_module,
        "load_passage_record",
        fake_load_passage_record,
    )
    monkeypatch.setattr(
        service_module,
        "get_connection",
        fake_get_connection,
    )
    monkeypatch.setattr(
        service_module,
        "fetch_passage_texts",
        fake_fetch_passage_texts,
    )

    service = make_service()

    result = service.inspect_passage(
        passage_id,
        representation=representation,
    )

    assert calls["load"] == {
        "db": service._db,
        "passage_id": passage_id,
        "representation": representation,
    }

    assert calls["application_name"] == "test-investigator"

    assert calls["fetch"] == {
        "connection": fake_connection,
        "records": [record],
    }

    assert result == {
        **record,
        "title": "A Test Document",
        "author": "Test Author",
        "filepath": "eebo/test.txt",
        "text": "This is the passage text.",
    }


def test_inspect_passage_propagates_missing_passage_error(monkeypatch):
    from mutatis_mutandis.core import VectorNotFoundError

    def fake_load_passage_record(db, passage_id, representation):
        raise VectorNotFoundError("Passage not found")

    monkeypatch.setattr(
        service_module,
        "load_passage_record",
        fake_load_passage_record,
    )

    service = make_service()

    try:
        service.inspect_passage("missing-passage")
    except VectorNotFoundError:
        pass
    else:
        raise AssertionError("Expected VectorNotFoundError")


