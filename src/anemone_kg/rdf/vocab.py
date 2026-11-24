"""Term registry and its verification against the defining vocabularies.

`model/terms.yaml` lists every class and property the graph may use. This
module checks each entry exists where it claims to come from:

=========  =================================================================
prefix     checked against
=========  =================================================================
dwc        TDWG term list (rs.tdwg.org/dwc/terms/, dcterms:hasPart), cached
dwciri     TDWG IRI term list (rs.tdwg.org/dwc/iri/), cached
dsw        Darwin-SW ontology (github.com/darwin-sw/dsw, dsw.owl), cached
sssom      SSSOM LinkML schema (slot names), cached
semapv     Semantic Mapping Vocabulary (semapv.owl), cached
akv        ontology/akv.ttl - must carry rdfs:comment or skos:definition
dcterms,   rdflib ClosedNamespace objects, generated from the W3C/DCMI
prov,      specifications; they raise on a term that does not exist
skos, dcat,
owl, rdfs
=========  =================================================================

Why: an IRI that does not exist in its vocabulary is silently accepted by any
RDF tool - it is just a string. Only an explicit check catches
`dwc:ocurrenceID` or a term remembered from an old version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import rdflib
import yaml
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDFS, SKOS

CLOSED = {"dcterms": DCTERMS, "prov": PROV, "skos": SKOS, "dcat": DCAT, "owl": OWL, "rdfs": RDFS}


@dataclass(frozen=True)
class Registry:
    prefixes: dict[str, str]
    terms: list[dict]

    def iri(self, curie: str) -> rdflib.URIRef:
        prefix, local = curie.split(":", 1)
        return rdflib.URIRef(self.prefixes[prefix] + local)

    @property
    def curies(self) -> set[str]:
        return {t["term"] for t in self.terms}


def load_registry(path: Path) -> Registry:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Registry(data["prefixes"], data["terms"])


@cache
def _graph(path: str, fmt: str | None = None) -> rdflib.Graph:
    return rdflib.Graph().parse(path, format=fmt)


@cache
def _tdwg_terms(path: str) -> frozenset[str]:
    g = _graph(path, "turtle")
    return frozenset(str(o) for o in g.objects(None, DCTERMS.hasPart))


@cache
def _sssom_names(path: str) -> frozenset[str]:
    y = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return frozenset(y.get("slots", {})) | frozenset(y.get("classes", {}))


def verify(reg: Registry, root: Path) -> dict[str, str]:
    """Return {curie: problem} for every registered term that cannot be verified."""
    vocab = root / "data" / "cache" / "vocab"
    problems: dict[str, str] = {}
    for t in reg.terms:
        curie = t["term"]
        prefix, local = curie.split(":", 1)
        iri = reg.iri(curie)
        if prefix == "dwc":
            ok = str(iri) in _tdwg_terms(str(vocab / "dwc-terms.ttl"))
        elif prefix == "dwciri":
            ok = str(iri) in _tdwg_terms(str(vocab / "dwciri-terms.ttl"))
        elif prefix == "dsw":
            ok = (iri, None, None) in _graph(str(vocab / "dsw.owl"))
        elif prefix == "semapv":
            ok = (iri, None, None) in _graph(str(vocab / "semapv.owl"))
        elif prefix == "sssom":
            ok = local in _sssom_names(str(vocab / "sssom_schema.yaml"))
        elif prefix == "akv":
            g = _graph(str(root / "ontology" / "akv.ttl"), "turtle")
            ok = any(g.objects(iri, RDFS.comment)) or any(g.objects(iri, SKOS.definition))
        elif prefix in CLOSED:
            try:
                ok = CLOSED[prefix][local] == iri
            except (AttributeError, KeyError):
                ok = False
        else:
            problems[curie] = f"no verification source for prefix {prefix!r}"
            continue
        if not ok:
            problems[curie] = f"not found in the {prefix} vocabulary"
    return problems


def jsonld_context(reg: Registry) -> dict:
    """JSON-LD @context from the registry prefixes (one source for both formats)."""
    ctx: dict = {k: v for k, v in reg.prefixes.items()}
    ctx["@version"] = 1.1
    return {"@context": ctx}


def write_context(reg: Registry, path: Path) -> None:
    path.write_text(json.dumps(jsonld_context(reg), indent=2) + "\n", encoding="utf-8")
