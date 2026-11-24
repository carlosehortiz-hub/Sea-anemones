"""SPARQL portability: the queries give the same answers in Oxigraph as in rdflib.

* In-process: pyoxigraph (the Oxigraph engine) loads the Turtle file and runs
  every query; no server needed, so this runs in every CI job.
* HTTP client: the Graph Store and SPARQL protocol calls, with mocked responses.
  The real server is exercised by the `endpoint` CI job (Docker).
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
import rdflib
import responses

from anemone_kg.config import load_config
from anemone_kg.endpoint import Endpoint, check, json_rows, normalise, rdflib_rows
from anemone_kg.stages.query import discover

XSD = "http://www.w3.org/2001/XMLSchema#"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def ttl(cfg):
    return cfg.path("processed") / "anemone_kg.ttl"


@pytest.fixture(scope="module")
def rdflib_graph(ttl):
    return rdflib.Graph().parse(ttl)


@pytest.fixture(scope="module")
def ox_store(ttl):
    store = ox.Store()
    store.load(path=str(ttl), format=ox.RdfFormat.TURTLE)
    return store


def ox_rows(store: ox.Store, text: str) -> set[tuple[str, ...]]:
    res = store.query(text)
    names = [v.value for v in res.variables]
    out = set()
    for sol in res:
        row = []
        for n in names:
            t = sol[n]
            dt = t.datatype.value if isinstance(t, ox.Literal) else None
            row.append(normalise(None if t is None else t.value, dt))
        out.add(tuple(row))
    return out


def test_same_triple_count(rdflib_graph, ox_store):
    assert len(ox_store) == len(rdflib_graph)


@pytest.mark.parametrize(
    "q", [q for q in discover(load_config().root) if q.kind == "sparql"], ids=lambda q: q.name
)
def test_query_gives_same_rows_in_oxigraph_and_rdflib(q, rdflib_graph, ox_store):
    assert ox_rows(ox_store, q.text) == rdflib_rows(rdflib_graph, q)


@pytest.mark.parametrize(
    ("value", "datatype", "expected"),
    [
        ("1.0E0", f"{XSD}double", "1"),
        ("1.0", f"{XSD}double", "1"),
        ("30", f"{XSD}integer", "30"),
        ("2026-11-24T12:46:16Z", f"{XSD}dateTime", "2026-11-24T12:46:16+00:00"),
        ("Exaiptasia pallida", None, "Exaiptasia pallida"),
    ],
)
def test_normalise_makes_engine_spellings_equal(value, datatype, expected):
    assert normalise(value, datatype) == expected


@responses.activate
def test_http_client_load_and_check(tmp_path, rdflib_graph, cfg):
    url = "http://oxigraph.test"
    ttl = tmp_path / "g.ttl"
    ttl.write_text("<http://e/s> <http://e/p> <http://e/o> .\n")
    responses.put(f"{url}/store?default", status=204)
    responses.post(
        f"{url}/query",
        json={
            "head": {"vars": ["n"]},
            "results": {
                "bindings": [{"n": {"type": "literal", "value": "1", "datatype": f"{XSD}integer"}}]
            },
        },
    )
    ep = Endpoint(url)
    ep.load(ttl)
    assert ep.count_triples() == 1
    assert responses.calls[0].request.headers["Content-Type"] == "text/turtle"

    # a wrong endpoint answer must be reported as a mismatch
    q = next(q for q in discover(cfg.root) if q.name == "q01_species_per_order")
    responses.post(
        f"{url}/query",
        json={"head": {"vars": ["order", "species", "markedInvalid"]}, "results": {"bindings": []}},
    )
    assert check(ep, rdflib_graph, [q]) != []


def test_json_rows_handles_unbound_values():
    payload = {
        "head": {"vars": ["a", "b"]},
        "results": {"bindings": [{"a": {"type": "literal", "value": "x"}}]},
    }
    assert json_rows(payload) == {("x", "")}
