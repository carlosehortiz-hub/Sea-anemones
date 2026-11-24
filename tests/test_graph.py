"""The knowledge graph: counts reconcile with the tables, no orphans, full provenance."""

from __future__ import annotations

import pytest
import rdflib
from rdflib import RDF, RDFS, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import PROV, SKOS

from anemone_kg.config import load_config
from anemone_kg.rdf.build import GraphBuilder, UnregisteredTermError, build_graph
from anemone_kg.rdf.vocab import load_registry
from anemone_kg.stages.validate import load_tables

DWC = rdflib.Namespace("http://rs.tdwg.org/dwc/terms/")
AKV = rdflib.Namespace("https://w3id.org/anemone-kg/vocab/")
OWL_AXIOM = URIRef("http://www.w3.org/2002/07/owl#Axiom")
DCT = rdflib.Namespace("http://purl.org/dc/terms/")


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def reg(cfg):
    return load_registry(cfg.root / "model" / "terms.yaml")


@pytest.fixture(scope="module")
def tables(cfg):
    return load_tables(cfg)


@pytest.fixture(scope="module")
def g(cfg, reg, tables):
    """Data graph only (without the akv vocabulary merged in)."""
    return build_graph(tables, reg, cfg.namespace["base"], cfg.source["doi"])


@pytest.fixture(scope="module")
def paper(cfg):
    return URIRef(f"https://doi.org/{cfg.source['doi']}")


def n_of(g, cls):
    return len(set(g.subjects(RDF.type, cls)))


def test_instance_counts_reconcile_with_tables(g, tables):
    t = tables
    assert n_of(g, DWC.Occurrence) == len(t["occurrence"]) + len(t["distribution"])
    assert n_of(g, DWC.Organism) == len(t["occurrence"])
    assert n_of(g, DWC.Identification) == len(t["identification"])
    assert n_of(g, DWC.Taxon) == len(t["taxon"]) + len(t["worms_record"])
    assert n_of(g, AKV.HabitatStatement) == len(t["habitat_statement"])
    m = t["taxon_mapping"]
    assert n_of(g, OWL_AXIOM) == int((m.status == "accepted").sum())


def test_only_registered_terms_are_emitted(g, reg):
    allowed = {reg.iri(x["term"]) for x in reg.terms} | {RDF.type}
    assert set(g.predicates()) <= allowed
    assert set(g.objects(None, RDF.type)) <= allowed


def test_builder_refuses_unregistered_terms(cfg, reg):
    b = GraphBuilder(reg, cfg.namespace["base"], cfg.source["doi"])
    s = URIRef("https://example.org/x")
    with pytest.raises(UnregisteredTermError):
        b.add(s, "dwc:vernacularName", "anemone")  # real DwC term, but not registered
    with pytest.raises(UnregisteredTermError):
        b.add(s, "a", URIRef("http://rs.tdwg.org/dwc/terms/MaterialEntity"))


def test_no_orphan_nodes(g, cfg):
    """Every project IRI used as an object is described (has a type) in the graph."""
    base = cfg.namespace["base"]
    objects = {
        o
        for o in g.objects()
        if isinstance(o, URIRef)
        and str(o).startswith(base)
        and not str(o).startswith(cfg.namespace["vocab"])
    }
    typed = set(g.subjects(RDF.type, None))
    assert objects - typed == set()


def test_external_nodes_are_labelled(g):
    """ENVO, GBIF and NCBI objects carry the label they had at resolution time."""
    for p in (SKOS.exactMatch, SKOS.closeMatch, URIRef("http://rs.tdwg.org/dwc/iri/habitat")):
        for o in g.objects(None, p):
            assert g.value(o, RDFS.label) is not None, o


@pytest.mark.parametrize(
    "cls", [DWC.Occurrence, DWC.Identification, DCT.Location, AKV.HabitatStatement]
)
def test_every_record_is_derived_from_the_paper_with_a_locator(g, paper, cls):
    for s in g.subjects(RDF.type, cls):
        assert (s, PROV.wasDerivedFrom, paper) in g, s
        d = g.value(s, PROV.qualifiedDerivation)
        assert d is not None and g.value(d, AKV.sourceLocator) is not None, s


def test_every_paper_taxon_is_derived_from_the_paper(g, paper, cfg):
    for s in g.subjects(RDF.type, DWC.Taxon):
        if str(s).startswith(cfg.namespace["base"]):
            assert (s, PROV.wasDerivedFrom, paper) in g


def test_every_identifier_link_has_resolution_provenance(g):
    for ax in g.subjects(RDF.type, OWL_AXIOM):
        resp = g.value(ax, PROV.wasDerivedFrom)
        assert g.value(resp, DCT.source) is not None
        assert g.value(resp, PROV.generatedAtTime) is not None
        act = g.value(ax, PROV.wasGeneratedBy)
        agents = set(g.objects(act, PROV.wasAssociatedWith))
        assert len(agents) == 2  # the pipeline and the external service


def test_synonym_chain(g):
    worms = "urn:lsid:marinespecies.org:taxname:"
    assert (URIRef(f"{worms}283486"), AKV.hasAcceptedName, URIRef(f"{worms}1264073")) in g
    assert g.value(URIRef(f"{worms}1264073"), DWC.scientificName) == rdflib.Literal(
        "Exaiptasia diaphana"
    )


def test_committed_serialisations_match_rebuild(cfg, g):
    vocab = rdflib.Graph().parse(cfg.root / "ontology" / "akv.ttl")
    full = g + vocab
    ttl = rdflib.Graph().parse(cfg.path("processed") / "anemone_kg.ttl")
    jsonld = rdflib.Graph().parse(cfg.path("processed") / "anemone_kg.jsonld", format="json-ld")
    assert isomorphic(full, ttl)
    assert isomorphic(ttl, jsonld)
