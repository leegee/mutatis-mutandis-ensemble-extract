
from __future__ import annotations

import pytest

from mutatis_mutandis.core import (
    VectorNotFoundError,
    load_passage_record,
    table_prefix,
)


def table_name(representation, start=1600, end=1699):
    return f"{table_prefix(representation)}{start}_{end}"


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.selected_columns = None
        self.where_clause = None
        self.limit_value = None

    def search(self):
        return self

    def where(self, clause):
        self.where_clause = clause
        return self

    def select(self, columns):
        self.selected_columns = columns
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def to_list(self):
        rows = self.rows

        if self.where_clause:
            prefix = "passage_id = '"

            assert self.where_clause.startswith(prefix)
            assert self.where_clause.endswith("'")

            passage_id = (
                self.where_clause[len(prefix):-1]
                .replace("''", "'")
            )

            rows = [
                row for row in rows
                if row["passage_id"] == passage_id
            ]

        if self.limit_value is not None:
            rows = rows[:self.limit_value]

        if self.selected_columns:
            rows = [
                {
                    key: row[key]
                    for key in self.selected_columns
                    if key in row
                }
                for row in rows
            ]

        return rows


class FakeDB:
    def __init__(self, tables):
        self.tables = tables

    def list_tables(self):
        return type(
            "TableList",
            (),
            {"tables": list(self.tables)},
        )()

    def open_table(self, name):
        return self.tables[name]


def passage_record(
    passage_id="passage-1",
    *,
    doc_id="doc-1",
    corpus="eebo",
    pub_year=1650,
    scale="broad",
):
    return {
        "passage_id": passage_id,
        "corpus": corpus,
        "doc_id": doc_id,
        "pub_year": pub_year,
        "scale": scale,
        "char_start": 100,
        "char_end": 200,
        "word_start": 10,
        "word_end": 30,
        "token_start": 15,
        "token_end": 35,
        "_distance": 0.123,
        "vector": [0.1, 0.2, 0.3],
    }


def test_load_passage_record_finds_record_in_matching_table():
    record = passage_record()

    db = FakeDB({
        table_name("l8", 1500, 1599): FakeTable([]),
        table_name("l8"): FakeTable([record]),
        table_name("l8", 1700, 1799): FakeTable([]),
        table_name("l4"): FakeTable([record]),
    })

    result = load_passage_record(
        db,
        "passage-1",
        representation="l8",
    )

    assert result["passage_id"] == "passage-1"
    assert result["doc_id"] == "doc-1"
    assert result["pub_year"] == 1650
    assert result["scale"] == "broad"
    assert result["table"] == table_name("l8")

    assert "vector" not in result
    assert "_distance" not in result


def test_load_passage_record_missing_raises():
    db = FakeDB({
        table_name("l8"): FakeTable([]),
    })

    with pytest.raises(VectorNotFoundError):
        load_passage_record(db, "missing")


def test_load_passage_record_duplicate_raises():
    record = passage_record()

    db = FakeDB({
        table_name("l8"): FakeTable([record]),
        table_name("l8", 1700, 1799): FakeTable([record]),
    })

    with pytest.raises(ValueError):
        load_passage_record(db, "passage-1")


def test_load_passage_record_escapes_quotes():
    passage_id = "passage-'quoted"

    record = passage_record(passage_id=passage_id)

    table = FakeTable([record])
    db = FakeDB({
        table_name("l8"): table,
    })

    result = load_passage_record(db, passage_id)

    assert result["passage_id"] == passage_id
    assert table.where_clause == (
        "passage_id = 'passage-''quoted'"
    )


def test_load_passage_record_uses_representation_prefix():
    l8 = passage_record(doc_id="l8-doc")
    l4 = passage_record(doc_id="l4-doc")

    db = FakeDB({
        table_name("l8"): FakeTable([l8]),
        table_name("l4"): FakeTable([l4]),
    })

    result = load_passage_record(
        db,
        "passage-1",
        representation="l4",
    )

    assert result["doc_id"] == "l4-doc"
    assert result["table"] == table_name("l4")
