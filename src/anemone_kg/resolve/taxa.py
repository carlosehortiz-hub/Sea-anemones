"""Taxon name resolution against WoRMS, GBIF and NCBI Taxonomy.

Each lookup produces one mapping row per (taxon, service), shaped after SSSOM
(Simple Standard for Sharing Ontological Mappings): subject = the paper's name
usage, object = the external record, plus predicate, justification, confidence
and the tool that produced it.

Acceptance policy - the same for every service:

* ``accepted``   exact, unique name match inside Cnidaria at the same rank;
* ``candidate``  a fuzzy/phonetic match. Never used as an identifier unless a
                 row in mappings/resolution_overrides.csv accepts it;
* ``ambiguous``  more than one record survives the filters;
* ``unresolved`` nothing matched (or offline cache miss).

Context filter: the paper is about Cnidaria (title), so homonyms in other
phyla are discarded. This is a documented rule, not a guess.

Homonym rule: when several WoRMS records in Cnidaria carry the same name, the
one whose authority equals the authority printed in the paper is kept
(compared after :func:`normalise_authority`). Without a printed authority, or
without a unique authority match, the row stays *ambiguous*.

Confidence: 1.0 for exact matches; GBIF's own score for GBIF; for WoRMS fuzzy
match types a fixed heuristic scale (phonetic 0.8, near_1 0.7, near_2 0.5,
near_3 0.3). These numbers have **no external source** - they only rank
candidates for review and never accept anything on their own.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from anemone_kg.resolve.http import CachedHttp, CachedResponse, CacheMiss

log = logging.getLogger(__name__)

PHYLUM = "Cnidaria"
WORMS = "https://www.marinespecies.org/rest"
GBIF = "https://api.gbif.org/v1/species/match"
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Heuristic, unsourced - see module docstring.
WORMS_FUZZY_CONFIDENCE = {"phonetic": 0.8, "near_1": 0.7, "near_2": 0.5, "near_3": 0.3}

EXACT = "skos:exactMatch"
CLOSE = "skos:closeMatch"
LEXICAL = "semapv:LexicalMatching"
CURATED = "semapv:ManualMappingCuration"


def normalise_authority(a: str | None) -> str:
    """'(Duchassaing & Michelotti, 1864a)' -> 'duchassaing michelotti 1864'.

    Drops parentheses (original vs current combination is not what identifies
    the name here), the letter suffix of a year (1864a), '&'/'and' and commas.
    """
    if not a:
        return ""
    s = re.sub(r"[()&,]", " ", a.lower()).replace(" and ", " ")
    s = re.sub(r"\b(\d{4})[a-z]\b", r"\1", s)
    return " ".join(s.split())


@dataclass
class TaxonMapping:
    subject_id: str
    subject_label: str
    predicate_id: str | None
    object_id: str | None
    object_label: str | None
    object_source: str
    match_type: (
        str  # exact_accepted | exact_synonym | exact_other | fuzzy | via_accepted_name | none
    )
    status: str  # accepted | candidate | ambiguous | unresolved
    confidence: float | None
    mapping_justification: str
    mapping_tool: str  # the request URL
    mapping_date: str | None
    cache_key: str | None
    query_name: str
    comment: str | None = None

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WormsRecord:
    """A WoRMS name record, kept as its own row so accepted names become graph nodes."""

    aphia_id: int
    scientific_name: str
    scientific_name_authorship: str | None
    taxonomic_status: str
    unaccept_reason: str | None
    valid_aphia_id: int | None
    valid_name: str | None
    worms_rank: str
    order: str | None
    family: str | None
    lsid: str
    url: str
    mapping_date: str
    cache_key: str

    @classmethod
    def from_json(cls, r: dict, resp: CachedResponse) -> WormsRecord:
        return cls(
            aphia_id=r["AphiaID"],
            scientific_name=r["scientificname"],
            scientific_name_authorship=r.get("authority"),
            taxonomic_status=r.get("status") or "",
            unaccept_reason=r.get("unacceptreason"),
            valid_aphia_id=r.get("valid_AphiaID"),
            valid_name=r.get("valid_name"),
            worms_rank=r.get("rank") or "",
            order=r.get("order"),
            family=r.get("family"),
            lsid=r["lsid"],
            url=r["url"],
            mapping_date=resp.retrieved_at,
            cache_key=resp.cache_key,
        )


@dataclass
class Override:
    service: str
    object_id: str
    decision: str  # accept | reject
    evidence: str


@dataclass
class TaxonResolver:
    http: CachedHttp
    overrides: dict[tuple[str, str], Override] = field(default_factory=dict)
    worms_records: dict[int, WormsRecord] = field(default_factory=dict)

    # ---------------------------------------------------------------- WoRMS
    def _worms_get(self, path: str, params: dict | None = None) -> CachedResponse:
        return self.http.get("worms", f"{WORMS}/{path}", params)

    def _keep(self, rec: dict, rank: str) -> bool:
        return rec.get("phylum") == PHYLUM and (rec.get("rank") or "").lower() == rank

    def _store(self, rec: dict, resp: CachedResponse) -> WormsRecord:
        wr = WormsRecord.from_json(rec, resp)
        self.worms_records.setdefault(wr.aphia_id, wr)
        return wr

    def _ensure_valid(self, wr: WormsRecord) -> None:
        """Fetch the accepted record for a synonym so it exists as its own node."""
        vid = wr.valid_aphia_id
        if vid and vid != wr.aphia_id and vid not in self.worms_records:
            resp = self._worms_get(f"AphiaRecordByAphiaID/{vid}")
            if resp.body:
                self._store(resp.body, resp)

    def worms(
        self, taxon_id: str, name: str, rank: str, authority: str | None = None
    ) -> TaxonMapping:
        base = dict(subject_id=taxon_id, subject_label=name, object_source="worms", query_name=name)
        try:
            resp = self._worms_get(
                f"AphiaRecordsByName/{name}", {"like": "false", "marine_only": "false"}
            )
        except CacheMiss as e:
            return self._unresolved(base, str(e), "offline cache miss")
        hits = [r for r in (resp.body or []) if self._keep(r, rank)]
        note = ""
        if len(hits) > 1 and authority:
            same = [
                h
                for h in hits
                if normalise_authority(h.get("authority")) == normalise_authority(authority)
            ]
            if len(same) == 1:
                others = ", ".join(
                    f"{h['AphiaID']} {h.get('authority')}" for h in hits if h is not same[0]
                )
                note = f"; homonym resolved by authority in paper ({authority}); not {others}"
                hits = same
        if len(hits) > 1:
            ids = ", ".join(str(h["AphiaID"]) for h in hits)
            return TaxonMapping(
                **base,
                predicate_id=None,
                object_id=None,
                object_label=None,
                match_type="none",
                status="ambiguous",
                confidence=None,
                mapping_justification=LEXICAL,
                mapping_tool=resp.url,
                mapping_date=resp.retrieved_at,
                cache_key=resp.cache_key,
                comment=f"homonyms in {PHYLUM}: AphiaID {ids}"
                + ("" if authority else "; no authority printed in the paper"),
            )
        if len(hits) == 1:
            wr = self._store(hits[0], resp)
            self._ensure_valid(wr)
            mt = (
                "exact_accepted"
                if wr.taxonomic_status == "accepted"
                else "exact_synonym"
                if wr.valid_aphia_id and wr.valid_aphia_id != wr.aphia_id
                else "exact_other"
            )
            return TaxonMapping(
                **base,
                predicate_id=EXACT,
                object_id=f"worms:{wr.aphia_id}",
                object_label=f"{wr.scientific_name} {wr.scientific_name_authorship or ''}".strip(),
                match_type=mt,
                status="accepted",
                confidence=1.0,
                mapping_justification=LEXICAL,
                mapping_tool=resp.url,
                mapping_date=resp.retrieved_at,
                cache_key=resp.cache_key,
                comment=f"WoRMS status: {wr.taxonomic_status}"
                + (f"; accepted name {wr.valid_name}" if mt == "exact_synonym" else "")
                + note,
            )
        return self._worms_fuzzy(base, name, rank, resp)

    def _worms_fuzzy(self, base: dict, name: str, rank: str, exact_resp: CachedResponse):
        resp = self._worms_get(
            "AphiaRecordsByMatchNames", {"scientificnames[]": name, "marine_only": "false"}
        )
        cands = [r for r in ((resp.body or [[]])[0] or []) if self._keep(r, rank)]
        if not cands:
            return self._unresolved(
                base, resp.url, "no exact or fuzzy match in Cnidaria", resp=resp
            )
        if len(cands) > 1:
            ids = ", ".join(f"{c['AphiaID']} {c['scientificname']}" for c in cands)
            return TaxonMapping(
                **base,
                predicate_id=None,
                object_id=None,
                object_label=None,
                match_type="fuzzy",
                status="ambiguous",
                confidence=None,
                mapping_justification=LEXICAL,
                mapping_tool=resp.url,
                mapping_date=resp.retrieved_at,
                cache_key=resp.cache_key,
                comment=f"several fuzzy candidates: {ids}",
            )
        c = cands[0]
        wr = self._store(c, resp)
        object_id = f"worms:{wr.aphia_id}"
        ov = self.overrides.get((base["subject_label"], object_id))
        status, just = "candidate", LEXICAL
        comment = f"WoRMS match_type {c.get('match_type')}; needs curation"
        if ov and ov.decision == "accept":
            status, just, comment = "accepted", CURATED, f"accepted by curator: {ov.evidence}"
            self._ensure_valid(wr)
        elif ov and ov.decision == "reject":
            status, comment = "unresolved", f"candidate rejected by curator: {ov.evidence}"
        return TaxonMapping(
            **base,
            predicate_id=CLOSE if status == "accepted" else None,
            object_id=object_id if status != "unresolved" else None,
            object_label=f"{wr.scientific_name} {wr.scientific_name_authorship or ''}".strip(),
            match_type="fuzzy",
            status=status,
            confidence=WORMS_FUZZY_CONFIDENCE.get(c.get("match_type"), 0.1),
            mapping_justification=just,
            mapping_tool=resp.url,
            mapping_date=resp.retrieved_at,
            cache_key=resp.cache_key,
            comment=comment,
        )

    # ----------------------------------------------------------------- GBIF
    def gbif(self, taxon_id: str, name: str, rank: str) -> TaxonMapping:
        base = dict(subject_id=taxon_id, subject_label=name, object_source="gbif", query_name=name)
        try:
            resp = self.http.get(
                "gbif",
                GBIF,
                {"name": name, "phylum": PHYLUM, "rank": rank.upper(), "verbose": "false"},
            )
        except CacheMiss as e:
            return self._unresolved(base, str(e), "offline cache miss")
        b = resp.body or {}
        mt, key = b.get("matchType", "NONE"), b.get("usageKey")
        ok_rank = (b.get("rank") or "").lower() == rank and b.get("phylum") == PHYLUM
        common = dict(
            mapping_tool=resp.url, mapping_date=resp.retrieved_at, cache_key=resp.cache_key
        )
        if mt == "EXACT" and ok_rank and b.get("canonicalName") == name:
            acc = b.get("acceptedUsageKey")
            return TaxonMapping(
                **base,
                predicate_id=EXACT,
                object_id=f"gbif:{key}",
                object_label=b.get("scientificName"),
                match_type="exact_synonym" if acc else "exact_accepted",
                status="accepted",
                confidence=b.get("confidence", 0) / 100,
                mapping_justification=LEXICAL,
                comment=f"GBIF status: {b.get('status')}"
                + (f"; acceptedUsageKey {acc} ({b.get('species')})" if acc else ""),
                **common,
            )
        if mt == "FUZZY" and ok_rank:
            return TaxonMapping(
                **base,
                predicate_id=None,
                object_id=f"gbif:{key}",
                object_label=b.get("scientificName"),
                match_type="fuzzy",
                status="candidate",
                confidence=b.get("confidence", 0) / 100,
                mapping_justification=LEXICAL,
                comment="GBIF fuzzy match; needs curation",
                **common,
            )
        return self._unresolved(
            base,
            resp.url,
            f"GBIF matchType {mt}" + ("" if ok_rank or mt == "NONE" else f", rank {b.get('rank')}"),
            resp=resp,
        )

    # ----------------------------------------------------------------- NCBI
    def _ncbi_lookup(self, name: str) -> tuple[list[str], CachedResponse]:
        resp = self.http.get(
            "ncbi",
            f"{NCBI}/esearch.fcgi",
            {"db": "taxonomy", "term": f"{name}[Scientific Name]", "retmode": "json"},
        )
        return (resp.body or {}).get("esearchresult", {}).get("idlist", []), resp

    def ncbi(self, taxon_id: str, name: str, rank: str, accepted_name: str | None) -> TaxonMapping:
        """Paper name first; if NCBI lacks it, the WoRMS accepted name (closeMatch)."""
        base = dict(subject_id=taxon_id, subject_label=name, object_source="ncbi")
        tries = [(name, EXACT, "exact_accepted")]
        if accepted_name and accepted_name != name:
            tries.append((accepted_name, CLOSE, "via_accepted_name"))
        last = None
        for query, pred, mt in tries:
            try:
                ids, resp = self._ncbi_lookup(query)
            except CacheMiss as e:
                return self._unresolved({**base, "query_name": query}, str(e), "offline cache miss")
            last = resp
            if len(ids) > 1:
                return TaxonMapping(
                    **base,
                    query_name=query,
                    predicate_id=None,
                    object_id=None,
                    object_label=None,
                    match_type="none",
                    status="ambiguous",
                    confidence=None,
                    mapping_justification=LEXICAL,
                    mapping_tool=resp.url,
                    mapping_date=resp.retrieved_at,
                    cache_key=resp.cache_key,
                    comment=f"taxids {ids}",
                )
            if len(ids) == 1:
                summ = self.http.get(
                    "ncbi",
                    f"{NCBI}/esummary.fcgi",
                    {"db": "taxonomy", "id": ids[0], "retmode": "json"},
                )
                rec = (summ.body or {}).get("result", {}).get(ids[0], {})
                if rec.get("scientificname") != query or rec.get("rank") != rank:
                    return self._unresolved(
                        {**base, "query_name": query},
                        summ.url,
                        f"NCBI {ids[0]} is {rec.get('scientificname')!r} "
                        f"({rec.get('rank')}), not {query!r} ({rank})",
                        resp=summ,
                    )
                return TaxonMapping(
                    **base,
                    query_name=query,
                    predicate_id=pred,
                    object_id=f"NCBITaxon:{ids[0]}",
                    object_label=rec["scientificname"],
                    match_type=mt,
                    status="accepted",
                    confidence=1.0,
                    mapping_justification=LEXICAL,
                    mapping_tool=summ.url,
                    mapping_date=summ.retrieved_at,
                    cache_key=summ.cache_key,
                    comment=f"NCBI division: {rec.get('division')}"
                    + ("; matched on WoRMS accepted name" if pred == CLOSE else ""),
                )
        return self._unresolved(
            {**base, "query_name": tries[-1][0]},
            last.url if last else "",
            "not in NCBI Taxonomy",
            resp=last,
        )

    # ---------------------------------------------------------------- utils
    @staticmethod
    def _unresolved(base: dict, tool: str, comment: str, resp: CachedResponse | None = None):
        return TaxonMapping(
            **base,
            predicate_id=None,
            object_id=None,
            object_label=None,
            match_type="none",
            status="unresolved",
            confidence=None,
            mapping_justification=LEXICAL,
            mapping_tool=tool,
            mapping_date=resp.retrieved_at if resp else None,
            cache_key=resp.cache_key if resp else None,
            comment=comment,
        )
