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
    assert conforms  # pySHACL with allow_warnings=True: no Violation
    res = results(report, data)
    assert res  # so sh:conforms in the strict sense of SHACL section 3.6 is false
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
    # 5. similarity score out of range
    axioms = sorted(g.subjects(RDF.type, OWL.Axiom))
    g.set((axioms[0], SSSOM.similarity_score, Literal(1.5, datatype=XSD.double)))
    faults["similarity"] = axioms[0]
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
    # 13. occurrence identifier that is not a UUIDv5 (OccurrenceShape)
    occ = specimens[3]
    g.set((occ, DWC.occurrenceID, Literal("specimen-4")))
    faults["bad_occurrence_id"] = occ
    # 14. identification qualifier outside the open-nomenclature list (IdentificationShape)
    ident = next(iter(sorted(g.subjects(RDF.type, DWC.Identification))))
    g.set((ident, DWC.identificationQualifier, Literal("aff. maybe")))
    faults["bad_qualifier"] = ident
    # 15. cached response without retrieval time (ResponseShape, via MappingShape)
    ax = axioms[2]
    resp = g.value(ax, PROV.wasDerivedFrom)
    g.remove((resp, PROV.generatedAtTime, None))
    faults["response_without_time"] = ax
    # 16. evidence tier that contradicts the evidence kind (AssertionShape)
    lit2 = sorted(g.subjects(rdflib.URIRef("http://purl.org/dc/terms/type"), AKV.Literature))[1]
    g.set((lit2, AKV.evidenceTier, AKV.SurveyVouchered))
    faults["tier_contradicts_kind"] = lit2
    # 17. a traced assertion that does not cite its specimen (AssertionShape; round 3)
    museum = sorted(g.subjects(AKV.evidenceTier, AKV.MuseumConfirmed))[0]
    g.remove((museum, AKV.citesSpecimen, None))
    faults["traced_without_specimen"] = museum
    # 18. a literature assertion typed as cited material (AssertionShape; round 3)
    lit3 = sorted(g.subjects(rdflib.URIRef("http://purl.org/dc/terms/type"), AKV.Literature))[2]
    g.set((lit3, DWC.basisOfRecord, Literal("MaterialCitation")))
    faults["literature_as_material"] = lit3
    # 19. two records of one service equated by the exactMatch closure (MappingShape; round 3:
    # curated spelling variants as exact links equated two WoRMS records of one name)
    ax19 = next(
        a
        for a in axioms[3:]
        if g.value(a, OWL.annotatedProperty) == SKOS.exactMatch
        and str(g.value(a, OWL.annotatedTarget)).startswith(WORMS)
    )
    target = g.value(ax19, OWL.annotatedTarget)
    other = next(
        o
        for o in sorted(g.objects(None, SKOS.exactMatch))
        if str(o).startswith(WORMS) and o != target
    )
    g.add((g.value(ax19, OWL.annotatedSource), SKOS.exactMatch, other))
    faults["exact_closure"] = ax19
    return g, faults


# Which node shape each fault exercises: every node shape must have a positive control.
FAULT_SHAPE = {
    "no_provenance": "DerivedFromPaper",
    "bad_catalog": "SpecimenShape",
    "two_current_ids": "OrganismShape",
    "lat_without_lon": "LocationShape",
    "similarity": "MappingShape",
    "exact_closure": "MappingShape",
    "traced_without_specimen": "AssertionShape",
    "literature_as_material": "AssertionShape",
    "mapping_without_triple": "MappingShape",
    "new_record_literature": "AssertionShape",
    "dangling_accepted_name": "WormsRecordShape",
    "bad_exact_match": "PaperTaxonShape",
    "untyped_date": "EventShape",
    "non_envo_habitat": "HabitatStatementShape",
    "page_out_of_range": "DerivationShape",
    "bad_occurrence_id": "OccurrenceShape",
    "bad_qualifier": "IdentificationShape",
    "response_without_time": "ResponseShape",
    "tier_contradicts_kind": "AssertionShape",
}


def test_every_node_shape_has_a_positive_control(shapes):
    """Review finding: 14 shapes but 12 faults, so two shapes (in fact three: Occurrence,
    Identification, Response) were never shown to fire."""
    declared = {
        str(s).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        for s in shapes.subjects(RDF.type, rdflib.URIRef("http://www.w3.org/ns/shacl#NodeShape"))
    }
    assert declared == set(FAULT_SHAPE.values())


@pytest.fixture(scope="module")
def broken_results(broken, shapes):
    g, _ = broken
    conforms, report = validate_graph(g, shapes)
    return conforms, results(report, g)


def test_broken_graph_does_not_conform(broken_results):
    assert broken_results[0] is False


@pytest.mark.parametrize("fault", sorted(FAULT_SHAPE))
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
