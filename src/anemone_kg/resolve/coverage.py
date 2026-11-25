"""Taxonomic acts, NCBI coverage and service releases: what the resolution layer rests on.

Three questions the identifier links alone do not answer:

1. *What kind of change* separates a name in the article from today's accepted name, and
   when was it made? WoRMS records the act as a source with a use ("new combination
   reference", "source of synonymy", "taxonomy source") and sometimes an ``unacceptreason``.
   The relation is classified from those fields; nothing is inferred from memory. Where
   WoRMS gives no act, the table says so.
2. Is a missing NCBI node a *coverage* result or a *query* artefact? The resolver queries
   ``[Scientific Name]``. Here every unresolved name is re-queried under all NCBI name
   classes (``[All Names]``: synonyms, misspellings, equivalent names), under every WoRMS
   synonym of its accepted name, and at genus level. For resolved taxa the number of INSDC
   nucleotide records is counted (``txid[Organism:exp]``), which is what "sequence data can
   be linked" would actually need. Per-marker counts are out of scope.
3. Which *release* of each service answered? GBIF backbone and ENVO versions and the NCBI
   Taxonomy database date are recorded next to the access date. WoRMS has no release
   number; its access date is the version.

Every call goes through the cached HTTP client, so the results are reproducible offline.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from anemone_kg.resolve.http import CachedHttp, CacheMiss

WORMS = "https://www.marinespecies.org/rest"
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GBIF_BACKBONE = "https://api.gbif.org/v1/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"
OLS_ENVO = "https://www.ebi.ac.uk/ols4/api/ontologies/envo"
ACT_USES = ("new combination reference", "source of synonymy", "taxonomy source")
_YEAR = re.compile(r"\(((?:17|18|19|20)\d\d)\)")


def _body(resp) -> Any:
    return resp.body if resp is not None else None


# ------------------------------------------------------------------- 1. taxonomic acts


def _epithet_stem(e: str) -> str:
    return re.sub(r"(us|a|um|is|e|i|ii|ae|orum|arum)$", "", e or "")


def relation(name: str, rec: pd.Series, valid_name: str | None) -> str:
    """Nomenclatural relation of an article name to its WoRMS accepted name."""
    status = str(rec.taxonomic_status)
    reason = str(rec.unaccept_reason) if pd.notna(rec.unaccept_reason) else ""
    if status == "nomen nudum":
        return "nomen nudum: unavailable name; the accepted name is the WoRMS editors' judgement"
    if status == "alternative representation":
        return "alternative representation in WoRMS (see text: ICZN Opinion 2500, 2023)"
    g1, *e1 = name.split()
    g2, *e2 = (valid_name or name).split()
    e1 = e1[0] if e1 else ""
    e2 = e2[0] if e2 else ""
    if g1 != g2 and _epithet_stem(e1) == _epithet_stem(e2):
        return "new combination (genus transfer)"
    if g1 == g2 and e1 != e2 and _epithet_stem(e1) == _epithet_stem(e2):
        return "gender agreement of the epithet (ICZN Art. 34.2)"
    if "subjective" in reason:
        return "subjective synonym"
    return "synonym"


def acts(http: CachedHttp, worms: pd.DataFrame) -> pd.DataFrame:
    """One row per unaccepted WoRMS record: relation, act source(s) and year(s)."""
    rows = []
    un = worms[worms.valid_aphia_id.notna() & (worms.valid_aphia_id != worms.aphia_id)]
    for r in un.sort_values("scientific_name").itertuples():
        resp = http.get("worms", f"{WORMS}/AphiaSourcesByAphiaID/{int(r.aphia_id)}")
        srcs = [s for s in (_body(resp) or []) if s.get("use") in ACT_USES]
        cites = []
        years = []
        for s in srcs:
            ref = s.get("reference") or ""
            m = _YEAR.search(ref)
            if m:
                years.append(int(m.group(1)))
            short = ref.split(". (")[0] if ". (" in ref else ref[:60]
            cites.append(f"{s['use']}: {short} ({m.group(1) if m else 'n.d.'})")
        reason = str(r.unaccept_reason) if pd.notna(r.unaccept_reason) else ""
        m = re.search(r"\b((?:17|18|19|20)\d\d)\b", reason)
        if m:
            years.append(int(m.group(1)))
            cites.append(f"unaccept reason: {reason}")
        rows.append(
            {
                "aphia_id": int(r.aphia_id),
                "name": r.scientific_name,
                "worms_status": r.taxonomic_status,
                "unaccept_reason": reason,
                "accepted_name": r.valid_name,
                "accepted_aphia_id": int(r.valid_aphia_id),
                "relation": relation(r.scientific_name, pd.Series(r._asdict()), r.valid_name),
                "act_sources": " | ".join(cites),
                "act_years": ", ".join(str(y) for y in sorted(set(years))),
                "timing": (
                    "not dated in WoRMS"
                    if not years
                    else "before 2016"
                    if max(years) < 2016
                    else "2016 or later"
                    if min(years) >= 2016
                    else "before and after 2016"
                ),
                "cache_key": resp.cache_key,
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 2. NCBI coverage


def _esearch(http: CachedHttp, db: str, term: str) -> tuple[int, list[str], str]:
    resp = http.get(
        "ncbi", f"{NCBI}/esearch.fcgi", {"db": db, "term": term, "retmode": "json", "retmax": 20}
    )
    res = (_body(resp) or {}).get("esearchresult", {})
    return int(res.get("count", 0)), res.get("idlist", []), resp.cache_key


def _synonyms(http: CachedHttp, aphia_id: int) -> list[str]:
    resp = http.get("worms", f"{WORMS}/AphiaSynonymsByAphiaID/{aphia_id}")
    return sorted({s["scientificname"] for s in (_body(resp) or []) if s.get("scientificname")})


def ncbi_coverage(
    http: CachedHttp, taxa: pd.DataFrame, mappings: pd.DataFrame, worms: pd.DataFrame
) -> pd.DataFrame:
    """Per name: NCBI result, retry outcome for unresolved names, nucleotide record count."""
    ncbi = mappings[mappings.object_source == "ncbi"].set_index("subject_id")
    wm = mappings[(mappings.object_source == "worms") & mappings.object_id.notna()]
    w_by_id = worms.set_index("aphia_id")
    rows = []
    for t in taxa.sort_values("scientific_name").itertuples():
        m = ncbi.loc[t.taxon_id]
        row: dict[str, Any] = {
            "name": t.scientific_name,
            "order": t.order,
            "family": t.family,
            "rank": t.taxon_rank,
            "ncbi_result": m.match_type if m.status == "accepted" else m.status,
            "taxid": m.object_id.split(":")[1] if isinstance(m.object_id, str) else None,
            "retry": None,
            "retry_hit": None,
            "genus_in_ncbi": None,
            "nucleotide_records": None,
        }
        if row["taxid"]:
            n, _, _ = _esearch(http, "nuccore", f"txid{row['taxid']}[Organism:exp]")
            row["nucleotide_records"] = n
        else:
            tried = [f"{t.scientific_name}[All Names]"]
            wrow = wm[wm.subject_id == t.taxon_id]
            if len(wrow):
                aid = int(wrow.object_id.iloc[0].split(":")[1])
                valid = w_by_id.valid_aphia_id.get(aid)
                for syn in _synonyms(http, int(valid) if pd.notna(valid) else aid):
                    tried.append(f"{syn}[All Names]")
            hit = None
            for term in tried:
                _, ids, _ = _esearch(http, "taxonomy", term)
                if ids:
                    summ = http.get(
                        "ncbi",
                        f"{NCBI}/esummary.fcgi",
                        {"db": "taxonomy", "id": ids[0], "retmode": "json"},
                    )
                    rec = (_body(summ) or {}).get("result", {}).get(ids[0], {})
                    hit = (
                        f"{term.removesuffix('[All Names]')} -> NCBI taxid {ids[0]} "
                        f"({rec.get('scientificname')})"
                    )
                    break
            row["retry"] = len(tried)
            row["retry_hit"] = hit or "none"
            if t.genus and t.taxon_rank == "species":
                _, ids, _ = _esearch(http, "taxonomy", f"{t.genus}[Scientific Name]")
                row["genus_in_ncbi"] = bool(ids)
        rows.append(row)
    return pd.DataFrame(rows)


def voucher_search(http: CachedHttp) -> dict:
    """INSDC nucleotide records that name the MOHBR collection (any field)."""
    out = {}
    for label, term in (
        ("MOHBR", "MOHBR[All Fields]"),
        ("Museo Oceanologico Hermano Benigno Roman", '"Hermano Benigno"[All Fields]'),
    ):
        n, _, key = _esearch(http, "nuccore", term)
        out[label] = {"term": term, "nucleotide_records": n, "cache_key": key}
    return out


# --------------------------------------------------------------------- 3. releases


def releases(http: CachedHttp) -> dict:
    out: dict[str, Any] = {}
    try:
        g = _body(http.get("gbif", GBIF_BACKBONE)) or {}
        out["gbif_backbone"] = {
            "dataset_key": g.get("key"),
            "title": g.get("title"),
            "version": g.get("version"),
            "pub_date": g.get("pubDate"),
            "modified": g.get("modified"),
            "license": g.get("license"),
        }
    except CacheMiss:
        out["gbif_backbone"] = None
    try:
        info = _body(http.get("ncbi", f"{NCBI}/einfo.fcgi", {"db": "taxonomy", "retmode": "json"}))
        db = (info or {}).get("einforesult", {}).get("dbinfo", [{}])[0]
        out["ncbi_taxonomy"] = {"last_update": db.get("lastupdate"), "count": db.get("count")}
    except CacheMiss:
        out["ncbi_taxonomy"] = None
    try:
        o = _body(http.get("ols", OLS_ENVO)) or {}
        cfg = o.get("config", {})
        out["envo"] = {
            "version": cfg.get("version"),
            "version_iri": cfg.get("versionIri"),
            "loaded": o.get("loaded"),
        }
    except CacheMiss:
        out["envo"] = None
    out["worms"] = {"version": "none published; the access date is the version"}
    return out


def to_markdown(changes: pd.DataFrame, cov: pd.DataFrame, rel: dict, vouchers: dict) -> str:
    unresolved = cov[cov.taxid.isna()]
    recovered = unresolved[unresolved.retry_hit != "none"]
    linked = cov[cov.taxid.notna()]
    out = [
        "# Taxonomic provenance: acts, NCBI coverage, service releases",
        "",
        "## Service releases",
        "",
        "| service | release |",
        "|---|---|",
        f"| GBIF Backbone Taxonomy | dataset {rel['gbif_backbone']['dataset_key']}, published "
        f"{rel['gbif_backbone']['pub_date'][:10]}, licence CC BY 4.0 |",
        f"| NCBI Taxonomy | database last updated {rel['ncbi_taxonomy']['last_update']} |",
        f"| ENVO (via OLS) | {rel['envo']['version_iri']} |",
        "| WoRMS | no release number; the access date of each cached response is the version |",
        "",
        "## Name changes between the article and WoRMS",
        "",
        "Relation classified from the WoRMS status, unaccept reason and names; act sources are "
        "the WoRMS sources whose use is a new combination, a synonymy or a taxonomy source.",
        "",
        changes.drop(columns=["cache_key"]).to_markdown(index=False),
        "",
        "## NCBI Taxonomy: retry of unresolved names",
        "",
        f"{len(unresolved)} names had no node under `[Scientific Name]`. Each was re-queried "
        "under all NCBI name classes (`[All Names]`) and under every WoRMS synonym of its "
        f"accepted name. {len(recovered)} have a node under another name class or a synonym; "
        "they are reported, not linked, because the node does not carry the printed name as "
        "its scientific name.",
        "",
        unresolved[["name", "order", "family", "retry", "retry_hit", "genus_in_ncbi"]].to_markdown(
            index=False
        ),
        "",
        "## INSDC nucleotide records per linked taxon",
        "",
        "Count of nucleotide records for the taxid and its descendants (`txid[Organism:exp]`). "
        "A taxid is a prerequisite for linking sequences by name, not evidence that sequences "
        "exist for a useful marker; per-marker counts are out of scope.",
        "",
        linked[["name", "order", "ncbi_result", "taxid", "nucleotide_records"]].to_markdown(
            index=False
        ),
        "",
        "## Sequences citing the MOHBR collection",
        "",
        *[
            f"- `{v['term']}` in INSDC nucleotide: {v['nucleotide_records']} records"
            for v in vouchers.values()
        ],
        "",
    ]
    return "\n".join(out)
