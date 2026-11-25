"""The term registry: every term exists in its vocabulary, and the checker rejects typos."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
import rdflib

from anemone_kg.config import load_config
from anemone_kg.rdf.vocab import jsonld_context, load_registry, verify


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def reg(cfg):
    return load_registry(cfg.root / "model" / "terms.yaml")


def test_every_registered_term_exists_in_its_vocabulary(cfg, reg):
    assert verify(reg, cfg.root) == {}


@pytest.mark.parametrize(
    "bad",
    [
        "dwc:ocurrenceID",  # typo in a DwC term
        "dwc:Location",  # DwC uses dcterms:Location, not dwc:Location
        "dwciri:acceptedNameUsage",  # no IRI version exists
        "dsw:hasTaxon",  # not a Darwin-SW term
        "skos:exactMatches",  # typo in a closed W3C namespace
        "prov:wasDerivedBy",  # plausible but non-existent PROV term
        "akv:undefinedTerm",  # project term without a definition
        # SSSOM slots whose IRI is not in the sssom: namespace (round 3: sssom:comment passed
        # because only slot names were checked; its IRI is rdfs:comment)
        "sssom:comment",
        "sssom:mapping_date",
    ],
)
def test_checker_rejects_terms_that_do_not_exist(cfg, reg, bad):
    probe = replace(reg, terms=[{"term": bad, "kind": "property", "use": "test"}])
    assert bad in verify(probe, cfg.root)


def test_registry_has_no_duplicates(reg):
    terms = [t["term"] for t in reg.terms]
    assert len(terms) == len(set(terms))


def test_project_vocabulary_is_minimal_and_documented(cfg, reg):
    akv = [t for t in reg.terms if t["term"].startswith("akv:")]
    schema = [t for t in akv if t["kind"] in ("class", "property")]
    values = [t for t in akv if t["kind"] == "individual"]
    # Classes and properties are what a reuser must learn; concept-scheme values are data.
    assert len(schema) <= 9, "the project namespace is growing; reuse first"
    assert len(values) <= 14, "two small concept schemes (evidence kinds and tiers) only"
    g = rdflib.Graph().parse(cfg.root / "ontology" / "akv.ttl")
    for t in akv:
        iri = reg.iri(t["term"])
        assert (iri, None, None) in g, t["term"]


def test_jsonld_context_is_generated_from_registry(cfg, reg):
    committed = json.loads((cfg.root / "ontology" / "context.jsonld").read_text())
    assert committed == jsonld_context(reg)
