"""SHACL shapes: the real graph conforms, and every shape catches the fault it exists for.

pySHACL takes ~10 s on the full graph, so all faults are injected into one
copy and validated once; each fault must then appear as its own violation.
"""

from __future__ import annotations

import pytest
import rdflib
from rdflib import RDF, XSD, Literal, Namespace, URIRef
from rdflib.namespace import PROV, SKOS

from anemone_kg.config import load_config
from anemone_kg.stages.shacl import results, validate_graph

DWC = Namespace("http://rs.tdwg.org/dwc/terms/")
DSW = Namespace("http://purl.org/dsw/")
AKV = Namespace("https://w3id.org/anemone-kg/vocab/")
SSSOM = Namespace("https://w3id.org/sssom/")
DWCIRI = Namespace("http://rs.tdwg.org/dwc/iri/")
OWL = Namespace("http://www.w3.org/2002/07/owl#")
WORMS = "urn:lsid:marinespecies.org:taxname:"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def data(cfg):
    return rdflib.Graph().parse(cfg.path("processed") / "anemone_kg.ttl")


@pytest.fixture(scope="module")
def shapes(cfg):
    return rdflib.Graph().parse(cfg.root / "shapes" / "anemone_kg.shapes.ttl")


def first(g, s=None, p=None, o=None):
    return next(iter(g.triples((s, p, o))))


def test_real_graph_conforms_with_expected_warnings(data, shapes):
    conforms, report = validate_graph(data, shapes)
    assert conforms
    res = results(report, data)
    assert not [r for r in res if r["severity"] == "Violation"]
    # same counts as the data-quality warnings W02+Open Sea, W03, W07, W04
    msgs = [r["message"] for r in res]
    assert sum("Event without a location" in m for m in msgs) == 4
    assert sum("'not identified'" in m for m in msgs) == 3
    assert sum("no ENVO term" in m for m in msgs) == 2
    assert sum("catalogue number" in m for m in msgs) == 1


@pytest.fixture(scope="module")
def broken(data):
    """One copy of the graph with twelve independent faults; returns (graph, {fault: node})."""
    g = rdflib.Graph() + data
    faults: dict[str, URIRef] = {}

    specimens = sorted(g.subjects(DWC.basisOfRecord, Literal("PreservedSpecimen")))
    # 1. record without provenance
    occ = specimens[0]
    g.remove((occ, PROV.wasDerivedFrom, None))
    faults["no_provenance"] = occ
    # 2. malformed catalogue number (SPARQL-targeted shape)
    occ = next(s for s in specimens[1:] if (s, DWC.catalogNumber, None) in g)
    g.set((occ, DWC.catalogNumber, Literal("1201")))
    faults["bad_catalog"] = occ
    # 3. an organism with two current identifications (SPARQL constraint)
    org = g.value(specimens[2], DSW.occurrenceOf)
    extra = URIRef("https://w3id.org/anemone-kg/identification/injected")
    g.add((extra, RDF.type, DWC.Identification))
    g.add((extra, DSW.identifies, org))
    faults["two_current_ids"] = org
    # 4. latitude without longitude
    loc = next(iter(sorted(g.subjects(DWC.decimalLatitude, None))))
    g.remove((loc, DWC.decimalLongitude, None))
    faults["lat_without_lon"] = loc
    # 5. confidence out of range
    axioms = sorted(g.subjects(RDF.type, OWL.Axiom))
    g.set((axioms[0], SSSOM.confidence, Literal(1.5, datatype=XSD.double)))
    faults["confidence"] = axioms[0]
    # 6. mapping record whose SKOS triple is missing
    ax = axioms[1]
    g.remove(
        (
            g.value(ax, OWL.annotatedSource),
            g.value(ax, OWL.annotatedProperty),
            g.value(ax, OWL.annotatedTarget),
        )
    )
    faults["mapping_without_triple"] = ax
    # 7. new country record on a literature assertion (SPARQL constraint)
    lit = next(
        iter(sorted(g.subjects(rdflib.URIRef("http://purl.org/dc/terms/type"), AKV.Literature)))
    )
    g.set((lit, AKV.isNewCountryRecord, Literal(True)))
    faults["new_record_literature"] = lit
    # 8. accepted-name pointer to a node that is not in the graph
    w = URIRef(f"{WORMS}283486")
    g.set((w, AKV.hasAcceptedName, URIRef(f"{WORMS}999999999")))
    faults["dangling_accepted_name"] = w
    # 9. taxon linked to a non-taxonomic IRI
    taxon = next(iter(sorted(g.subjects(DWC.taxonID, None))))
    g.add((taxon, SKOS.exactMatch, URIRef("https://example.org/not-a-taxon")))
    faults["bad_exact_match"] = taxon
    # 10. untyped event date
    ev = next(iter(sorted(g.subjects(DWC.eventDate, None))))
    g.set((ev, DWC.eventDate, Literal("16/02/1995")))
    faults["untyped_date"] = ev
    # 11. habitat pointing outside ENVO
    hs = next(iter(sorted(g.subjects(DWCIRI.habitat, None))))
    g.add((hs, DWCIRI.habitat, URIRef("https://example.org/reef")))
    faults["non_envo_habitat"] = hs
    # 12. page outside the paper
    d = next(iter(sorted(g.subjects(AKV.sourcePage, None))))
    g.set((d, AKV.sourcePage, Literal(99, datatype=XSD.positiveInteger)))
    faults["page_out_of_range"] = d
    return g, faults


@pytest.fixture(scope="module")
def broken_results(broken, shapes):
    g, _ = broken
    conforms, report = validate_graph(g, shapes)
    return conforms, results(report, g)


def test_broken_graph_does_not_conform(broken_results):
    assert broken_results[0] is False


@pytest.mark.parametrize(
    "fault",
    [
        "no_provenance",
        "bad_catalog",
        "two_current_ids",
        "lat_without_lon",
        "confidence",
        "mapping_without_triple",
        "new_record_literature",
        "dangling_accepted_name",
        "bad_exact_match",
        "untyped_date",
        "non_envo_habitat",
        "page_out_of_range",
    ],
)
def test_each_injected_fault_is_a_violation(broken, broken_results, fault):
    _, faults = broken
    node = str(faults[fault])
    hits = [r for r in broken_results[1] if r["severity"] == "Violation" and r["focus"] == node]
    assert hits, f"{fault}: no violation reported on {node}"


def test_report_markdown_is_deterministic(cfg, monkeypatch, tmp_path):
    """Bug: blank-node property paths were printed with random ids, so CI's
    stale-output check failed on reports/shacl_report.md."""
    from anemone_kg.stages import shacl as stage

    monkeypatch.setattr(
        type(cfg),
        "path",
        lambda self, key: tmp_path if key == "reports" else self.root / self.raw["paths"][key],
    )
    stage.shacl(cfg)
    first = (tmp_path / "shacl_report.md").read_text()
    stage.shacl(cfg)
    assert first == (tmp_path / "shacl_report.md").read_text()
    assert r"dwciri:habitat \| dwciri:substrate" in first  # escaped for the table
    assert "<n" not in first  # no blank-node ids
