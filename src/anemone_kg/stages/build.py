"""Stage 5 - build: validated canonical tables -> RDF (Turtle + JSON-LD)."""

from __future__ import annotations

import json
import logging
from collections import Counter

import rdflib
from rdflib import RDF

from anemone_kg.cli import stage
from anemone_kg.config import Config
from anemone_kg.rdf.build import build_graph
from anemone_kg.rdf.vocab import jsonld_context, load_registry
from anemone_kg.stages.validate import load_tables

log = logging.getLogger(__name__)


def graph_for(cfg: Config) -> rdflib.Graph:
    reg = load_registry(cfg.root / "model" / "terms.yaml")
    vocab = rdflib.Graph().parse(cfg.root / "ontology" / "akv.ttl")
    return build_graph(load_tables(cfg), reg, cfg.namespace["base"], cfg.source["doi"], vocab)


def stable_jsonld(text: str) -> str:
    """Sort nodes by @id and multi-valued properties by value.

    rdflib's JSON-LD writer orders nodes and value arrays by hash iteration, so
    two runs on the same graph differ textually. CI fails on any regenerated
    output that differs from the committed one, so the file must be canonical.
    """
    doc = json.loads(text)

    def key(v):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)

    def norm(node):
        if isinstance(node, dict):
            return {k: norm(v) for k, v in sorted(node.items())}
        if isinstance(node, list):
            return sorted((norm(v) for v in node), key=key)
        return node

    graph = doc.get("@graph", [])
    doc["@graph"] = sorted((norm(n) for n in graph), key=lambda n: n.get("@id", key(n)))
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def summary(g: rdflib.Graph) -> dict:
    classes = Counter(g.namespace_manager.normalizeUri(o) for o in g.objects(None, RDF.type))
    preds = Counter(g.namespace_manager.normalizeUri(p) for p in g.predicates())
    return {
        "triples": len(g),
        "subjects": len(set(g.subjects())),
        "instances_per_class": dict(sorted(classes.items())),
        "triples_per_predicate": dict(sorted(preds.items())),
    }


@stage("build")
def build(cfg: Config) -> None:
    g = graph_for(cfg)
    out = cfg.path("processed")
    ttl = out / "anemone_kg.ttl"
    g.serialize(ttl, format="turtle")
    reg = load_registry(cfg.root / "model" / "terms.yaml")
    jsonld = g.serialize(
        format="json-ld", context=jsonld_context(reg)["@context"], sort_keys=True, indent=1
    )
    (out / "anemone_kg.jsonld").write_text(stable_jsonld(jsonld), encoding="utf-8")
    s = summary(g)
    (cfg.path("reports") / "graph_summary.json").write_text(
        json.dumps(s, indent=2) + "\n", encoding="utf-8"
    )
    log.info(
        "[build] %d triples, %d subjects -> %s and .jsonld",
        s["triples"],
        s["subjects"],
        ttl.relative_to(cfg.root),
    )
    for cls, n in s["instances_per_class"].items():
        log.info("[build]   %-28s %5d", cls, n)
