"""Build the knowledge graph from the canonical, validated tables.

The model is documented in docs/modelling_decisions.md. Three properties of
this builder matter more than any single triple:

1. **Registry-guarded.** Every predicate and every rdf:type class goes through
   :meth:`GraphBuilder.add`, which refuses terms not listed in
   model/terms.yaml. Those terms are verified against their vocabularies, so
   the graph cannot contain an invented or misspelled IRI.
2. **Traceable.** Every record node gets ``prov:wasDerivedFrom`` the paper's
   DOI and a qualified derivation with the locator in the paper (table, row,
   page) and the pipeline stage. Every identifier link gets an SSSOM mapping
   record pointing to the cached API response it came from.
3. **Deterministic.** IRIs are minted from the canonical UUIDv5 ids, never
   from row order, so rebuilding gives the same graph.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import pandas as pd
from rdflib import RDF, XSD, BNode, Graph, Literal, Namespace, URIRef

from anemone_kg import __version__
from anemone_kg.dq.crosstable import (
    IDENTIFICATION_CHANGE,
    evidence_tiers,
    identification_changes,
    supporting_specimens,
)
from anemone_kg.rdf.vocab import Registry

DOI_IRI = "https://doi.org/{doi}"
SERVICE_INFO = {
    "worms": ("WoRMS REST API", "https://www.marinespecies.org/rest/"),
    "gbif": ("GBIF species API", "https://api.gbif.org/v1/species/"),
    "ncbi": ("NCBI E-utilities (Taxonomy)", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    "ols": ("EBI Ontology Lookup Service (ENVO)", "https://www.ebi.ac.uk/ols4/"),
}
STAGES = (
    "extract",
    "canonicalize",
    "resolve-worms",
    "resolve-gbif",
    "resolve-ncbi",
    "annotate-envo",
    "build",
)
EVIDENCE = {
    "this_survey": "ThisSurvey",
    "mohbr_collection": "MohbrCollection",
    "literature": "Literature",
}


WORMS_STATUS = {"accepted": "accepted", "unaccepted": "synonym"}


class UnregisteredTermError(ValueError):
    """The builder tried to emit a term that is not in model/terms.yaml."""


SIMILARITY = {
    "worms": "WoRMS fuzzy match type on a project ordinal scale (phonetic 0.8, near_1 0.7, "
    "near_2 0.5, near_3 0.3); orders candidates only, not calibrated",
    "gbif": "GBIF species/match confidence scaled to 0-1; not calibrated",
}


def _genus(name) -> str:
    return str(name).split()[0] if isinstance(name, str) and name else ""


def mapping_method(r) -> str:
    """How a mapping was made, in words (the first part of the SSSOM comment, rdfs:comment)."""
    curated = r.mapping_justification == "semapv:ManualMappingCuration"
    if r.match_type == "via_accepted_name":
        cross = _genus(r.subject_label) != _genus(r.object_label)
        return (
            "NCBI fallback by chaining: article name -> WoRMS accepted name -> the NCBI node "
            f"carrying that name ({r.object_label}), queried in the NCBI scientific-name class; "
            "no circumscription claim; crosses a genus change: " + ("yes" if cross else "no")
        )
    if curated and r.match_type == "fuzzy":
        return (
            "curated orthographic or gender variant of the record's name (skos:closeMatch, so "
            "that no transitive closure equates records of one service; evidence follows)"
        )
    if curated:
        return (
            "curated link to one of several homonymous records: the article prints no "
            "authority, so the usage cannot be identified (skos:closeMatch; evidence follows)"
        )
    if r.match_type == "fuzzy":
        return "fuzzy candidate accepted by the curator (evidence follows)"
    if isinstance(r.comment, str) and "resolved by authority" in r.comment:
        return "exact name; WoRMS homonym resolved by the authority printed in the article"
    if r.match_type == "exact_synonym":
        return "exact name of an unaccepted record (synonym or variant) in the service"
    if r.object_source == "ncbi":
        return "exact name, unique in NCBI Taxonomy at the same rank ([Scientific Name] class)"
    return "exact name, unique within Cnidaria at the same rank"


def mapping_comment(r) -> str:
    """SSSOM ``comment`` (slot_uri rdfs:comment): the method, then the curator's evidence."""
    ev = r.comment if isinstance(r.comment, str) and r.comment else None
    return mapping_method(r) + (f". Evidence: {ev}" if ev else "")


def mapping_tool(source: str) -> str:
    return f"anemone-kg resolve, {SERVICE_INFO[source][0]} client"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _present(v) -> bool:
    return (
        v is not None
        and not (isinstance(v, float) and v != v)
        and v is not pd.NA
        and not (isinstance(v, str) and v == "")
    )


@dataclass
class GraphBuilder:
    reg: Registry
    base: str
    doi: str
    g: Graph = field(default_factory=Graph)

    def __post_init__(self) -> None:
        self.ak = Namespace(self.base)
        self.ns = {k: Namespace(v) for k, v in self.reg.prefixes.items()}
        for k, v in self.reg.prefixes.items():
            self.g.bind(k, v)
        self._props = {self.reg.iri(t["term"]) for t in self.reg.terms if t["kind"] == "property"}
        self._classes = {self.reg.iri(t["term"]) for t in self.reg.terms if t["kind"] == "class"}
        self.paper = URIRef(DOI_IRI.format(doi=self.doi))

    # ------------------------------------------------------------- core
    def t(self, curie: str) -> URIRef:
        return self.reg.iri(curie)

    def add(self, s, curie: str, o) -> None:
        """Add one triple; refuse unregistered predicates and classes. Skip empty values."""
        if not _present(o):
            return
        p = RDF.type if curie == "a" else self.t(curie)
        if curie == "a":
            if o not in self._classes:
                raise UnregisteredTermError(f"class {o} not in model/terms.yaml")
        elif p not in self._props:
            raise UnregisteredTermError(f"property {curie} not in model/terms.yaml")
        if not isinstance(o, (URIRef, Literal, BNode)):
            o = Literal(o)
        self.g.add((s, p, o))

    def iri(self, kind: str, local: str) -> URIRef:
        return self.ak[f"{kind}/{local}"]

    def derived(self, s: URIRef, source_ref: str, page, activity: str) -> None:
        """prov:wasDerivedFrom the paper + a qualified derivation with the locator."""
        self.add(s, "prov:wasDerivedFrom", self.paper)
        d = URIRef(f"{s}#derivation")
        self.add(s, "prov:qualifiedDerivation", d)
        self.add(d, "a", self.t("prov:Derivation"))
        self.add(d, "prov:entity", self.paper)
        self.add(d, "prov:hadActivity", self.iri("activity", activity))
        self.add(d, "akv:sourceLocator", Literal(source_ref))
        if _present(page):
            self.add(d, "akv:sourcePage", Literal(int(page), datatype=XSD.positiveInteger))

    # ------------------------------------------------- provenance frame
    def frame(self, source: pd.Series, accepted_services: Iterable[str]) -> None:
        P = self.paper
        self.add(P, "a", self.t("dcterms:BibliographicResource"))
        self.add(P, "a", self.t("prov:Entity"))
        self.add(P, "dcterms:identifier", Literal(f"doi:{self.doi}"))
        self.add(P, "dcterms:bibliographicCitation", Literal(source.bibliographic_citation))
        self.add(P, "dcterms:license", URIRef("https://creativecommons.org/licenses/by/4.0/"))

        pdf = self.iri("file", "source-pdf")
        self.add(pdf, "a", self.t("prov:Entity"))
        self.add(pdf, "dcterms:identifier", Literal(f"sha256:{source.sha256}"))
        self.add(pdf, "prov:wasDerivedFrom", P)
        self.add(pdf, "rdfs:label", Literal("Publisher PDF of the source paper"))

        agent = self.iri("agent", "anemone-kg")
        self.add(agent, "a", self.t("prov:SoftwareAgent"))
        self.add(agent, "rdfs:label", Literal(f"anemone-kg pipeline {__version__}"))
        for svc in accepted_services:
            name, url = SERVICE_INFO[svc]
            a = self.iri("agent", svc)
            self.add(a, "a", self.t("prov:SoftwareAgent"))
            self.add(a, "rdfs:label", Literal(name))
            self.add(a, "rdfs:seeAlso", URIRef(url))
        for stage in STAGES:
            act = self.iri("activity", stage)
            self.add(act, "a", self.t("prov:Activity"))
            self.add(act, "rdfs:label", Literal(f"pipeline stage: {stage}"))
            self.add(act, "prov:wasAssociatedWith", agent)
            svc = {
                "resolve-worms": "worms",
                "resolve-gbif": "gbif",
                "resolve-ncbi": "ncbi",
                "annotate-envo": "ols",
            }.get(stage)
            if svc:
                self.add(act, "prov:wasAssociatedWith", self.iri("agent", svc))
        self.add(self.iri("activity", "extract"), "prov:used", pdf)

        ds = self.iri("dataset", "anemone-kg")
        self.add(ds, "a", self.t("dcat:Dataset"))
        self.add(
            ds,
            "dcterms:title",
            Literal(
                "Coastal sea anemones of Venezuela: knowledge graph derived from "
                "González-Muñoz et al. (2016)",
                lang="en",
            ),
        )
        self.add(
            ds, "dcterms:license", URIRef("https://creativecommons.org/publicdomain/zero/1.0/")
        )
        self.add(ds, "prov:hadPrimarySource", P)
        self.add(ds, "prov:wasGeneratedBy", self.iri("activity", "build"))

    # ------------------------------------------------------------ names
    def taxa(self, taxa: pd.DataFrame) -> None:
        for r in taxa.itertuples():
            s = self.iri("taxon", r.taxon_id)
            self.add(s, "a", self.t("dwc:Taxon"))
            self.add(s, "dwc:taxonID", Literal(r.taxon_id))
            self.add(s, "rdfs:label", Literal(r.scientific_name))
            self.add(s, "dwc:scientificName", Literal(r.scientific_name))
            self.add(s, "dwc:scientificNameAuthorship", r.scientific_name_authorship)
            self.add(s, "dwc:taxonRank", Literal(r.taxon_rank))
            self.add(s, "dwc:genus", r.genus)
            self.add(s, "dwc:specificEpithet", r.specific_epithet)
            self.add(s, "dwc:family", r.family)
            self.add(s, "dwc:order", r.order)
            # A name usage: the name as used in the article, not a concept.
            self.add(s, "dwc:nameAccordingTo", Literal("González-Muñoz et al. (2016)"))
            if bool(r.flag_invalid_in_source):
                # '†' in Table 1: "species currently considered as invalid" (legend, p. 6).
                # Not a GBIF TaxonomicStatus value, so it is a remark, not a status.
                self.add(
                    s,
                    "dwc:taxonRemarks",
                    Literal("Marked † in Table 1: 'species currently considered as invalid'"),
                )
            self.add(s, "akv:hasDoubtfulPreviousRecords", Literal(bool(r.flag_doubtful_in_source)))
            self.derived(s, r.source_ref, r.source_page, "canonicalize")

    def worms_records(self, worms: pd.DataFrame) -> None:
        for r in worms.itertuples():
            s = URIRef(r.lsid)
            self.add(s, "a", self.t("dwc:Taxon"))
            self.add(s, "rdfs:label", Literal(r.scientific_name))
            self.add(s, "dwc:scientificName", Literal(r.scientific_name))
            self.add(s, "dwc:scientificNameAuthorship", r.scientific_name_authorship)
            self.add(s, "dwc:scientificNameID", Literal(r.lsid))
            # WoRMS statuses mapped to the GBIF TaxonomicStatus vocabulary where one fits
            status = str(r.taxonomic_status)
            if status in WORMS_STATUS:
                self.add(s, "dwc:taxonomicStatus", Literal(WORMS_STATUS[status]))
            elif status == "nomen nudum":
                self.add(s, "dwc:nomenclaturalStatus", Literal("nomen nudum"))
            else:
                self.add(s, "dwc:taxonRemarks", Literal(f"WoRMS status: {status}"))
            self.add(
                s,
                "dwc:nameAccordingTo",
                Literal(f"World Register of Marine Species (accessed {str(r.mapping_date)[:10]})"),
            )
            self.add(s, "dwc:taxonRank", Literal(str(r.worms_rank).lower()))
            self.add(s, "dwc:family", r.family)
            self.add(s, "dwc:order", r.order)
            self.add(s, "rdfs:seeAlso", URIRef(r.url))
            if _present(r.valid_aphia_id):
                valid = URIRef(f"{self.reg.prefixes['worms']}{int(r.valid_aphia_id)}")
                self.add(s, "dwc:acceptedNameUsageID", Literal(str(valid)))
                self.add(s, "dwc:acceptedNameUsage", r.valid_name)
                self.add(s, "akv:hasAcceptedName", valid)

    def object_iri(self, curie: str) -> URIRef:
        prefix, local = curie.split(":", 1)
        return URIRef(self.reg.prefixes[prefix] + local)

    def mappings(self, m: pd.DataFrame) -> None:
        for r in m[m.status == "accepted"].itertuples():
            subj = self.iri("taxon", r.subject_id)
            obj = self.object_iri(r.object_id)
            self.add(subj, r.predicate_id, obj)  # the plain SKOS link
            if r.object_source == "worms" and r.predicate_id == "skos:exactMatch":
                # only an identical name gets the record's LSID as its scientificNameID
                self.add(subj, "dwc:scientificNameID", Literal(str(obj)))
            else:
                self.add(obj, "rdfs:label", r.object_label)
            ax = self.iri("mapping", f"{r.subject_id}/{r.object_source}")
            self.add(ax, "a", self.t("owl:Axiom"))
            self.add(ax, "owl:annotatedSource", subj)
            self.add(ax, "owl:annotatedProperty", self.t(r.predicate_id))
            self.add(ax, "owl:annotatedTarget", obj)
            self.add(ax, "sssom:mapping_justification", self.t(r.mapping_justification))
            if r.match_type == "fuzzy":
                # A fuzzy score orders candidates; it is not a probability that the accepted
                # mapping is right (that rests on the curator's evidence, in rdfs:comment).
                self.add(
                    ax, "sssom:similarity_score", Literal(float(r.confidence), datatype=XSD.double)
                )
                self.add(ax, "sssom:similarity_measure", Literal(SIMILARITY[r.object_source]))
            # Exact and accepted-name matches carry no confidence: the comment says how the
            # link was made, and a constant 1 would claim more than a lexical match. The
            # method goes in rdfs:comment, SSSOM's slot_uri for `comment`, so that an SSSOM
            # parser keeps it; the request URL stays in the provenance of the response.
            self.add(ax, "sssom:mapping_tool", Literal(mapping_tool(r.object_source)))
            self.add(ax, "sssom:mapping_tool_version", Literal(__version__))
            self.add(ax, "dcterms:created", Literal(str(r.mapping_date)[:10], datatype=XSD.date))
            self.add(ax, "rdfs:comment", Literal(mapping_comment(r)))
            self.add(ax, "prov:wasGeneratedBy", self.iri("activity", f"resolve-{r.object_source}"))
            self.response(ax, r.cache_key, r.mapping_tool, r.mapping_date)

    def response(self, s: URIRef, cache_key, url, when) -> None:
        if not _present(cache_key):
            return
        resp = self.iri("response", str(cache_key).removesuffix(".json"))
        self.add(s, "prov:wasDerivedFrom", resp)
        self.add(resp, "a", self.t("prov:Entity"))
        self.add(resp, "rdfs:label", Literal(f"cached API response data/cache/{cache_key}"))
        self.add(resp, "dcterms:source", Literal(url, datatype=XSD.anyURI))
        if _present(when):
            self.add(resp, "prov:generatedAtTime", Literal(when, datatype=XSD.dateTime))

    # ----------------------------------------------------------- places
    def locations(self, loc: pd.DataFrame) -> None:
        regions = {}
        for reg_name in sorted(loc.region.dropna().unique()):
            rr = self.iri("location", f"region-{_slug(reg_name)}")
            regions[reg_name] = rr
            self.add(rr, "a", self.t("dcterms:Location"))
            self.add(rr, "dwc:locality", Literal(reg_name))
            self.add(rr, "rdfs:label", Literal(reg_name))
            self.add(rr, "dwc:countryCode", Literal("VE"))
            self.derived(rr, "Table 1, header (coastal region)", 3, "extract")
        for r in loc.itertuples():
            s = self.iri("location", r.locality_id)
            self.add(s, "a", self.t("dcterms:Location"))
            self.add(s, "dwc:locationID", Literal(r.locality_id))
            self.add(s, "rdfs:label", Literal(r.locality_name))
            self.add(s, "dwc:locality", Literal(r.locality_name))
            self.add(s, "dwc:verbatimLocality", Literal(r.verbatim_locality))
            self.add(s, "dwc:stateProvince", r.state_province)
            self.add(s, "dwc:countryCode", Literal(r.country_code))
            if _present(r.decimal_latitude):
                self.add(
                    s,
                    "dwc:decimalLatitude",
                    Literal(f"{r.decimal_latitude:.6f}", datatype=XSD.decimal),
                )
                self.add(
                    s,
                    "dwc:decimalLongitude",
                    Literal(f"{r.decimal_longitude:.6f}", datatype=XSD.decimal),
                )
            self.add(s, "dwc:verbatimCoordinates", r.verbatim_coordinates)
            if _present(r.decimal_latitude):
                # Table 2 prints DMS to 0.01 arc-second and states no datum; no uncertainty is
                # recorded, and none is invented here.
                self.add(s, "dwc:geodeticDatum", Literal("not recorded"))
                self.add(s, "dwc:coordinatePrecision", Literal("0.000003", datatype=XSD.decimal))
            if _present(r.sampled_in_study):
                self.add(s, "akv:sampledInStudy", Literal(bool(r.sampled_in_study)))
            if _present(r.parent_locality_id):
                self.add(s, "dcterms:isPartOf", self.iri("location", r.parent_locality_id))
            if _present(r.region):
                self.add(s, "dcterms:isPartOf", regions[r.region])
            self.derived(s, r.source_ref, r.source_page, "canonicalize")

    # -------------------------------------------------------- specimens
    @staticmethod
    def _date(v):
        if not _present(v):
            return None
        return Literal(
            v, datatype=XSD.date if len(v) == 10 else XSD.gYearMonth if len(v) == 7 else XSD.gYear
        )

    def specimens(self, occ: pd.DataFrame, ident: pd.DataFrame, changes: dict) -> None:
        cur_taxon = ident[ident.is_current].set_index("occurrence_id").taxon_id
        prev_name = ident[~ident.is_current].set_index("occurrence_id").verbatim_name
        museum = set(occ[occ.record_source == "table3"].occurrence_id)
        for r in occ.itertuples():
            s = self.iri("occurrence", r.occurrence_id)
            ev = self.iri("event", r.occurrence_id)
            org = self.iri("organism", r.occurrence_id)
            self.add(s, "a", self.t("dwc:Occurrence"))
            self.add(s, "dwc:occurrenceID", Literal(r.occurrence_id))
            self.add(s, "dwc:basisOfRecord", Literal(r.basis_of_record))
            self.add(s, "dwc:institutionCode", r.institution_code)
            self.add(s, "dwc:catalogNumber", r.catalog_number)
            self.add(s, "dwc:otherCatalogNumbers", r.other_catalog_numbers)
            self.add(s, "dwc:recordedBy", r.recorded_by)
            self.add(s, "dwc:occurrenceRemarks", r.occurrence_remarks)
            if r.occurrence_id in prev_name.index:
                self.add(s, "dwc:previousIdentifications", Literal(prev_name[r.occurrence_id]))
            self.add(
                s,
                "rdfs:label",
                Literal(
                    f"{r.institution_code} {r.catalog_number}"
                    if _present(r.catalog_number)
                    else f"field code {r.other_catalog_numbers}"
                ),
            )
            self.add(s, "dsw:atEvent", ev)
            self.add(s, "dsw:occurrenceOf", org)
            tid = cur_taxon.get(r.occurrence_id)
            if _present(tid):
                self.add(s, "dwciri:toTaxon", self.iri("taxon", tid))
            self.add(ev, "a", self.t("dwc:Event"))
            self.add(ev, "dwc:eventDate", self._date(r.event_date))
            self.add(ev, "dwc:verbatimEventDate", r.verbatim_event_date)
            if _present(r.locality_id):
                self.add(ev, "dsw:locatedAt", self.iri("location", r.locality_id))
            self.add(org, "a", self.t("dwc:Organism"))
            self.derived(s, r.source_ref, r.source_page, "canonicalize")

        prev = ident[~ident.is_current].set_index("occurrence_id").identification_id
        page_of = dict(zip(occ.occurrence_id, occ.source_page, strict=True))
        for r in ident.itertuples():
            s = self.iri("identification", r.identification_id)
            self.add(s, "a", self.t("dwc:Identification"))
            self.add(s, "dsw:identifies", self.iri("organism", r.occurrence_id))
            if _present(r.taxon_id):
                self.add(s, "dwciri:toTaxon", self.iri("taxon", r.taxon_id))
            self.add(s, "dwc:verbatimIdentification", Literal(r.verbatim_name))
            self.add(s, "dwc:identificationQualifier", r.identification_qualifier)
            self.add(s, "dwc:identificationRemarks", r.identification_remarks)
            why = changes.get(r.occurrence_id)
            if why and not r.is_current:
                self.add(
                    s,
                    "dwc:identificationRemarks",
                    Literal(
                        f"Previous identification; change: {why} ({IDENTIFICATION_CHANGE[why]})"
                    ),
                )
            if r.is_current and r.occurrence_id in museum:
                self.add(
                    s,
                    "dwc:identificationVerificationStatus",
                    Literal(
                        "unverified: could not be corroborated"
                        if why == "unverified"
                        else "examined by the source authors (external morphology)"
                    ),
                )
            self.add(
                s,
                "rdfs:label",
                Literal(
                    f"{'current' if r.is_current else 'superseded'} identification: "
                    f"{r.verbatim_name}"
                ),
            )
            if r.is_current and r.occurrence_id in prev.index:
                self.add(s, "prov:wasRevisionOf", self.iri("identification", prev[r.occurrence_id]))
            self.derived(s, r.source_ref, page_of[r.occurrence_id], "canonicalize")

    # --------------------------------------------------------- Table 1
    def references(self, ref: pd.DataFrame) -> None:
        for r in ref.itertuples():
            s = self.iri("reference", r.reference_code)
            if r.evidence_kind == "literature":
                self.add(s, "a", self.t("dcterms:BibliographicResource"))
            self.add(s, "a", self.t("prov:Entity"))
            self.add(s, "rdfs:label", Literal(r.short_citation))
            self.add(s, "dcterms:bibliographicCitation", Literal(r.short_citation))
            self.derived(s, f"{r.source_ref}, code '{r.reference_code}'", r.source_page, "extract")

    def distribution(
        self,
        d: pd.DataFrame,
        refs: pd.DataFrame,
        tiers: pd.Series,
        support: dict,
        occ: pd.DataFrame,
    ) -> None:
        cites = dict(zip(refs.reference_code, refs.short_citation, strict=True))
        label = {
            o: f"{i}:{c}" if _present(c) else f"field code {f}"
            for o, i, c, f in zip(
                occ.occurrence_id,
                occ.institution_code,
                occ.catalog_number,
                occ.other_catalog_numbers,
                strict=True,
            )
        }
        for r in d.itertuples():
            s = self.iri("distribution", r.distribution_id)
            ev = self.iri("event", r.distribution_id)
            self.add(s, "a", self.t("dwc:Occurrence"))
            self.add(s, "dwc:occurrenceID", Literal(r.distribution_id))
            self.add(s, "dwc:basisOfRecord", Literal(r.basis_of_record))
            self.add(s, "dwc:occurrenceStatus", Literal("present"))
            self.add(s, "dwciri:toTaxon", self.iri("taxon", r.taxon_id))
            self.add(s, "dcterms:type", self.t(f"akv:{EVIDENCE[r.evidence_kind]}"))
            self.add(s, "akv:evidenceTier", self.t(f"akv:{tiers[r.distribution_id]}"))
            for oid in support.get(r.distribution_id, []):
                # the specimen occurrence(s) behind this assertion; avoids double counting
                self.add(s, "akv:citesSpecimen", self.iri("occurrence", oid))
            if support.get(r.distribution_id):
                self.add(
                    s,
                    "dwc:associatedOccurrences",
                    Literal(
                        " | ".join(
                            f"(cited specimen) {label[o]}" for o in support[r.distribution_id]
                        )
                    ),
                )
            if _present(r.reference_code):
                self.add(s, "dcterms:references", self.iri("reference", r.reference_code))
                self.add(s, "dwc:associatedReferences", Literal(cites[r.reference_code]))
            else:
                self.add(
                    s,
                    "dwc:associatedReferences",
                    Literal("González-Muñoz et al. (2016), this survey"),
                )
            self.add(s, "akv:isNewCountryRecord", Literal(bool(r.is_new_record)))
            self.add(s, "dwc:occurrenceRemarks", r.occurrence_remarks)
            self.add(s, "dsw:atEvent", ev)
            self.add(ev, "a", self.t("dwc:Event"))
            if _present(r.locality_id):
                self.add(ev, "dsw:locatedAt", self.iri("location", r.locality_id))
            self.derived(s, r.source_ref, r.source_page, "canonicalize")

    # ---------------------------------------------------------- habitat
    def habitats(self, hs: pd.DataFrame, ann: pd.DataFrame) -> None:
        acc = ann[ann.status == "accepted"]
        for r in hs.itertuples():
            s = self.iri("habitat", r.habitat_statement_id)
            self.add(s, "a", self.t("akv:HabitatStatement"))
            self.add(s, "dcterms:subject", self.iri("taxon", r.taxon_id))
            self.add(s, "dwc:habitat", Literal(r.habitat_text, lang="en"))
            self.derived(s, r.source_ref, r.source_page, "extract")
            for a in acc[acc.habitat_statement_id == r.habitat_statement_id].itertuples():
                envo = self.object_iri(a.envo_id)
                prop = "dwciri:substrate" if a.habitat_kind == "substrate" else "dwciri:habitat"
                self.add(s, prop, envo)
                self.add(envo, "rdfs:label", Literal(a.envo_label, lang="en"))
            if (acc.habitat_statement_id == r.habitat_statement_id).any():
                self.add(s, "prov:wasGeneratedBy", self.iri("activity", "annotate-envo"))


def build_graph(
    tables: dict[str, pd.DataFrame], reg: Registry, base: str, doi: str, vocab: Graph | None = None
) -> Graph:
    b = GraphBuilder(reg, base, doi)
    m = tables["taxon_mapping"]
    services = [*sorted(set(m.loc[m.status == "accepted", "object_source"])), "ols"]
    b.frame(tables["source_document"].iloc[0], services)
    b.taxa(tables["taxon"])
    b.worms_records(tables["worms_record"])
    b.mappings(m)
    b.locations(tables["locality"])
    occ = tables["occurrence"]
    b.specimens(occ, tables["identification"], identification_changes(tables))
    b.references(tables["reference"])
    b.distribution(
        tables["distribution"],
        tables["reference"],
        evidence_tiers(tables),
        supporting_specimens(tables),
        occ,
    )
    b.habitats(tables["habitat_statement"], tables["habitat_annotation"])
    if vocab is not None:  # project vocabulary travels with the data
        b.g += vocab
    return b.g
