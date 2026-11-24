"""Queries: every file is documented, runs, and SPARQL and SQL agree on the same question."""

from __future__ import annotations

import pandas as pd
import pytest

from anemone_kg.config import load_config
from anemone_kg.stages.query import discover, run_all

# (SPARQL query, SQL query) pairs that answer the same question.
PAIRS = [
    ("q01_species_per_order", "s01_species_per_order"),
    ("q02_new_records_by_locality", "s03_new_records_by_locality"),
    ("q03_accepted_name_differs", "s02_accepted_name_differs"),
]


@pytest.fixture(scope="module")
def results():
    return run_all(load_config())


def _rows(df: pd.DataFrame) -> set[tuple]:
    def norm(v):
        if v is None or (isinstance(v, float) and v != v):
            return ""
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)

    return {tuple(norm(v) for v in row) for row in df.itertuples(index=False)}


def test_between_six_and_eight_sparql_and_two_or_three_sql_queries():
    qs = discover(load_config().root)
    assert 6 <= sum(q.kind == "sparql" for q in qs) <= 8
    assert 2 <= sum(q.kind == "sql" for q in qs) <= 3


def test_every_query_is_documented_and_returns_rows(results):
    for name, (q, df) in results.items():
        assert q.title and q.question and q.why, name
        assert len(df) > 0, f"{name} returned no rows"


@pytest.mark.parametrize(("sparql", "sql"), PAIRS)
def test_sparql_and_sql_agree(results, sparql, sql):
    assert _rows(results[sparql][1]) == _rows(results[sql][1])


def test_known_answers(results):
    q01 = results["q01_species_per_order"][1].set_index("order")
    assert int(q01.loc["Actiniaria", "species"]) == 30
    q02 = results["q02_new_records_by_locality"][1]
    assert set(q02.loc[q02.newRecords > 0, "newRecordTaxa"]) == {
        "Anthopleura pallida",
        "Telmatactis vernonia",
    }
    q06 = results["q06_reidentified_specimens"][1]
    assert len(q06) == 25
    q05 = results["q05_provenance_of_a_record"][1]
    assert set(q05.sourceLocator) == {"Table 3, row 2"} and len(q05) == 3
