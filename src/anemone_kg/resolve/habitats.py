"""Habitat paragraphs -> ENVO terms.

Two steps, kept apart on purpose:

1. **Phrase -> ENVO label** comes from a curated vocabulary
   (mappings/habitat_vocabulary.csv). A human decides that "seagrass meadows"
   means ENVO's *sea grass bed*; code never invents that link.
2. **ENVO label -> IRI** is looked up in the EBI Ontology Lookup Service by
   exact label. The IRI is never typed by hand; if OLS does not return a term
   whose label equals the curated label, the annotation is *unresolved*.

Negation guard: "mostly in shallow waters, but not intertidal zones" must not
yield *intertidal zone*. A match is dropped when "not" or "never" occurs in
the few words before it, and the drop is recorded.

What is *not* mapped: biotic substrates (sponges, hermit-crab shells, seagrass
leaves as attachment surface) and phrases with no ENVO class (coral rubble).
They are listed in the report so the gap is visible.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import pandas as pd

from anemone_kg.resolve.http import CachedHttp, CacheMiss

OLS = "https://www.ebi.ac.uk/ols4/api/search"
NEGATION = re.compile(r"\b(not|never|no)\b(?:\W+\w+){0,3}\W*$", re.IGNORECASE)


@dataclass
class EnvoTerm:
    label: str
    envo_id: str | None
    iri: str | None
    status: str  # accepted | unresolved
    mapping_tool: str
    mapping_date: str | None
    cache_key: str | None


@dataclass
class HabitatAnnotation:
    habitat_statement_id: str
    taxon_id: str
    matched_text: str
    char_start: int
    char_end: int
    phrase_pattern: str
    envo_label: str
    envo_id: str | None
    habitat_kind: str
    status: str  # accepted | unresolved | negated
    mapping_justification: str
    mapping_tool: str
    mapping_date: str | None
    cache_key: str | None
    comment: str | None

    def as_row(self) -> dict:
        return asdict(self)


class EnvoLookup:
    def __init__(self, http: CachedHttp) -> None:
        self.http = http
        self.cache: dict[str, EnvoTerm] = {}

    def term(self, label: str) -> EnvoTerm:
        if label in self.cache:
            return self.cache[label]
        params = {
            "q": label,
            "ontology": "envo",
            "queryFields": "label",
            "exact": "true",
            "fieldList": "iri,label,obo_id",
            "rows": 5,
        }
        try:
            resp = self.http.get("ols", OLS, params)
        except CacheMiss as e:
            t = EnvoTerm(label, None, None, "unresolved", str(e), None, None)
        else:
            docs = (resp.body or {}).get("response", {}).get("docs", [])
            exact = [
                d
                for d in docs
                if d.get("label", "").lower() == label.lower()
                and (d.get("obo_id") or "").startswith("ENVO:")
            ]
            ids = {d["obo_id"] for d in exact}
            if len(ids) == 1:
                d = exact[0]
                t = EnvoTerm(
                    label,
                    d["obo_id"],
                    d["iri"],
                    "accepted",
                    resp.url,
                    resp.retrieved_at,
                    resp.cache_key,
                )
            else:
                t = EnvoTerm(
                    label, None, None, "unresolved", resp.url, resp.retrieved_at, resp.cache_key
                )
        self.cache[label] = t
        return t


def annotate(
    statements: pd.DataFrame, vocabulary: pd.DataFrame, envo: EnvoLookup
) -> list[HabitatAnnotation]:
    out: list[HabitatAnnotation] = []
    for st in statements.itertuples():
        text = st.habitat_text
        seen: set[tuple[str, int]] = set()
        for v in vocabulary.itertuples():
            for m in re.finditer(v.phrase_regex, text, flags=re.IGNORECASE):
                key = (v.envo_label, m.start())
                if key in seen:
                    continue
                seen.add(key)
                negated = NEGATION.search(text[max(0, m.start() - 40) : m.start()])
                term = envo.term(v.envo_label)
                status = "negated" if negated else term.status
                comment = (
                    f"preceded by negation: '{negated.group(0).strip()}'"
                    if negated
                    else None
                    if term.status == "accepted"
                    else "ENVO label not found by exact match in OLS"
                )
                out.append(
                    HabitatAnnotation(
                        habitat_statement_id=st.habitat_statement_id,
                        taxon_id=st.taxon_id,
                        matched_text=m.group(0),
                        char_start=m.start(),
                        char_end=m.end(),
                        phrase_pattern=v.phrase_regex,
                        envo_label=v.envo_label,
                        envo_id=term.envo_id if status == "accepted" else None,
                        habitat_kind=v.kind,
                        status=status,
                        mapping_justification="semapv:ManualMappingCuration",
                        mapping_tool=term.mapping_tool,
                        mapping_date=term.mapping_date,
                        cache_key=term.cache_key,
                        comment=comment,
                    )
                )
    return out
