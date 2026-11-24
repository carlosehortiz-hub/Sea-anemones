"""A SPARQL endpoint for the graph: load it into Oxigraph and check the queries.

Two W3C protocols, nothing Oxigraph-specific:

* **load** - SPARQL 1.1 Graph Store HTTP Protocol: ``PUT /store?default`` with
  the Turtle file replaces the default graph (idempotent).
* **check** - SPARQL 1.1 Protocol: each ``queries/*.rq`` is POSTed to
  ``/query`` and the JSON results are compared with rdflib's answers on the
  same file. Any difference fails, so the queries are shown to be portable
  SPARQL rather than rdflib dialect.

Comparison is on *normalised* values: engines may write the same literal
differently (``1.0`` vs ``1.0E0`` for an xsd:double, ``+00:00`` vs ``Z``), and
rows are compared as sets because ORDER BY ties may be broken differently.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import rdflib
import requests

from anemone_kg.config import load_config
from anemone_kg.stages.query import Query, discover

log = logging.getLogger(__name__)

XSD = "http://www.w3.org/2001/XMLSchema#"
NUMERIC = {
    f"{XSD}{t}"
    for t in (
        "integer",
        "decimal",
        "double",
        "float",
        "int",
        "long",
        "positiveInteger",
        "nonNegativeInteger",
    )
}
DEFAULT_URL = "http://localhost:7878"

Row = tuple[str, ...]


def normalise(value: str | None, datatype: str | None = None) -> str:
    """Engine-independent form of one result value."""
    if value is None:
        return ""
    if datatype in NUMERIC:
        try:
            return format(Decimal(value).normalize(), "f")  # 30, not 3E+1
        except InvalidOperation:
            return value
    if datatype == f"{XSD}dateTime":
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return value
    return value


def rdflib_rows(g: rdflib.Graph, q: Query) -> set[Row]:
    res = g.query(q.text)
    out = set()
    for row in res:
        vals = []
        for v in row:
            dt = str(v.datatype) if isinstance(v, rdflib.Literal) and v.datatype else None
            vals.append(normalise(None if v is None else str(v), dt))
        out.add(tuple(vals))
    return out


def json_rows(payload: dict) -> set[Row]:
    """Rows from a SPARQL 1.1 JSON results document."""
    names = payload["head"]["vars"]
    out = set()
    for b in payload["results"]["bindings"]:
        out.add(
            tuple(normalise(b[n]["value"], b[n].get("datatype")) if n in b else "" for n in names)
        )
    return out


@dataclass
class Endpoint:
    url: str = DEFAULT_URL
    timeout_s: float = 60

    def load(self, ttl: Path) -> None:
        resp = requests.put(
            f"{self.url}/store?default",
            data=ttl.read_bytes(),
            headers={"Content-Type": "text/turtle"},
            timeout=self.timeout_s,
        )
        resp.raise_for_status()

    def count_triples(self) -> int:
        q = "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"
        return int(self.select(q)["results"]["bindings"][0]["n"]["value"])

    def select(self, text: str) -> dict:
        resp = requests.post(
            f"{self.url}/query",
            data=text.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            timeout=self.timeout_s,
        )
        resp.raise_for_status()
        return resp.json()


def check(endpoint: Endpoint, graph: rdflib.Graph, queries: list[Query]) -> list[str]:
    """Run every SPARQL query on the endpoint and on rdflib; return mismatches."""
    problems = []
    for q in (q for q in queries if q.kind == "sparql"):
        remote = json_rows(endpoint.select(q.text))
        local = rdflib_rows(graph, q)
        status = "same" if remote == local else "DIFFERENT"
        log.info("[endpoint] %-40s %4d rows  %s", q.name, len(remote), status)
        if remote != local:
            problems.append(
                f"{q.name}: only endpoint {sorted(remote - local)[:3]}, "
                f"only rdflib {sorted(local - remote)[:3]}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="anemone_kg endpoint",
        description="Load the graph into a SPARQL endpoint and check the queries against it.",
    )
    p.add_argument("action", choices=["load", "check"])
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--config", default=None)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    ttl = cfg.path("processed") / "anemone_kg.ttl"
    ep = Endpoint(args.url)
    if args.action == "load":
        ep.load(ttl)
        n = ep.count_triples()
        expected = len(rdflib.Graph().parse(ttl))
        log.info("[endpoint] loaded %d triples into %s (file has %d)", n, args.url, expected)
        return 0 if n == expected else 1
    problems = check(ep, rdflib.Graph().parse(ttl), discover(cfg.root))
    for msg in problems:
        log.error("[endpoint] %s", msg)
    return 1 if problems else 0
