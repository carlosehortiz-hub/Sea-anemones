"""Why each cross-table warning (W08-W11) fires: cause, link sensitivity, shift signature.

The four cross-source rules compare Table 1 codes with the specimen tables. A row they flag
can have several causes, and only some of them say anything about the source article:

* the specimen table and Table 1 use different names for the same taxon (a nomenclatural
  update), or the specimen is identified only above species level;
* the specimen was re-identified, and Table 1 kept the previous identification;
* the flag depends on a site-to-area link that the curator judged, not the article;
* an extraction error (a code read into the wrong column) - excluded here only because the
  extraction census found no disagreement, and checked again below by the shift signature;
* none of these: the two tables really differ as printed.

Each flagged row is given exactly one cause, in the order above (the first that applies).
The classification is deterministic and uses only the canonical tables; it is reported, not
applied - no row is changed.

Link sensitivity: the rules are re-run with every *uncertain* site-to-area link (a curated
link that is not an exact name match or a printed park name) set to linked, and then to
unlinked, so a reader can see how much of each count rests on those judgements.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from anemone_kg.dq.rules import Tables, _w08, _w09, _w10, _w11

CERTAIN_LINK_RULES = {"exact", "park_name"}

CAUSES = {
    "nomenclatural": "same taxon under another name (WoRMS accepted name agrees)",
    "above_species": "a specimen of the same family is identified only above species level",
    "reidentified": "re-identified in Table 3; Table 1 keeps the previous identification",
    "unconfirmed": "Table 3 could not confirm the identification ('not identified')",
    "link": "depends on an uncertain site-to-area link",
    "other_code": "Table 1 lists the taxon in this area, but under another code",
    "as_printed": "the tables differ as printed (no other cause applies)",
}

RULES: dict[str, tuple[Callable[[Tables], pd.DataFrame], str, str]] = {
    "W08": (_w08, "this_survey", "table2"),
    "W09": (_w09, "this_survey", "table2"),
    "W10": (_w10, "mohbr_collection", "table3"),
    "W11": (_w11, "mohbr_collection", "table3"),
}


def accepted_ids(t: Tables) -> dict[str, int]:
    """taxon_id -> WoRMS accepted AphiaID (via the matched record's valid AphiaID)."""
    m = t["taxon_mapping"]
    m = m[(m.object_source == "worms") & m.object_id.notna()]
    w = t["worms_record"].set_index("aphia_id")
    out = {}
    for sid, oid in zip(m.subject_id, m.object_id, strict=True):
        aid = int(oid.split(":")[1])
        valid = w.valid_aphia_id.get(aid)
        out[sid] = int(valid) if pd.notna(valid) else aid
    return out


def _area_col(t: Tables) -> dict[str, str]:
    """area locality_id -> Table 1 column id (T1A02 ...), from the header locator."""
    loc = t["locality"]
    areas = loc[loc.locality_level == "area"]
    out = {}
    for lid, ref in zip(areas.locality_id, areas.source_ref, strict=True):
        parts = ref.split()  # "Table 1, header, block A col 2"
        out[lid] = f"T1{parts[-3]}{int(parts[-1]):02d}"
    return out


def relink(t: Tables, crosswalk: pd.DataFrame, scenario: str) -> Tables:
    """Tables with uncertain Table 3 site links all set to 'linked' or 'unlinked'."""
    if scenario == "as_curated":
        return t
    loc = t["locality"].copy()
    col_area = {v: k for k, v in _area_col(t).items()}
    cw = crosswalk[crosswalk.source_table == "table3"]
    uncertain = cw[~cw.rule.isin(CERTAIN_LINK_RULES) & cw.table1_locality_col_id.notna()]
    for key, col in zip(uncertain.verbatim_key, uncertain.table1_locality_col_id, strict=True):
        is_site = (loc.locality_level == "site") & (loc.verbatim_locality == key)
        loc.loc[is_site, "parent_locality_id"] = (
            col_area.get(col) if scenario == "all_linked" else None
        )
    return {**t, "locality": loc}


def sensitivity(t: Tables, crosswalk: pd.DataFrame) -> pd.DataFrame:
    cw = crosswalk[crosswalk.source_table == "table3"]
    n_uncertain = int((~cw.rule.isin(CERTAIN_LINK_RULES) & cw.table1_locality_col_id.notna()).sum())
    rows = []
    for scenario in ("all_unlinked", "as_curated", "all_linked"):
        tt = relink(t, crosswalk, scenario)
        rows.append(
            {"scenario": scenario, **{rid: len(fn(tt)) for rid, (fn, _, _) in RULES.items()}}
        )
    df = pd.DataFrame(rows)
    df.attrs["uncertain_links"] = n_uncertain
    return df


def _specimens(t: Tables, source: str) -> pd.DataFrame:
    """Specimens of one table with area, current and previous taxon."""
    occ = t["occurrence"][t["occurrence"].record_source == source]
    ident = t["identification"]
    cur = ident[ident.is_current][["occurrence_id", "taxon_id", "verbatim_name"]]
    prev = ident[~ident.is_current][["occurrence_id", "taxon_id", "verbatim_name"]].rename(
        columns={"taxon_id": "prev_taxon_id", "verbatim_name": "prev_name"}
    )
    loc = t["locality"][["locality_id", "parent_locality_id"]]
    return (
        occ.merge(cur, on="occurrence_id", how="left")
        .merge(prev, on="occurrence_id", how="left")
        .merge(loc, on="locality_id", how="left")
        .rename(columns={"parent_locality_id": "area_id"})
    )


def classify(t: Tables, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """One row per W08-W11 flag, with its cause and the evidence for it."""
    acc = accepted_ids(t)
    names = dict(zip(t["taxon"].taxon_id, t["taxon"].scientific_name, strict=True))
    rank = dict(zip(t["taxon"].taxon_id, t["taxon"].taxon_rank, strict=True))
    family = dict(
        zip(
            t["taxon"].taxon_id,
            t["taxon"].family.fillna(t["taxon"].scientific_name),  # a family-level taxon
            strict=True,
        )
    )
    loc_name = dict(zip(t["locality"].locality_id, t["locality"].locality_name, strict=True))
    area_col = _area_col(t)
    dist = t["distribution"]
    linked_all = relink(t, crosswalk, "all_linked")
    flagged_linked = {rid: fn(linked_all) for rid, (fn, _, _) in RULES.items()}

    cw3 = crosswalk[crosswalk.source_table == "table3"]
    uncertain_keys = set(cw3.loc[~cw3.rule.isin(CERTAIN_LINK_RULES), "verbatim_key"])
    site_uncertain = dict(
        zip(
            t["locality"].locality_id,
            t["locality"].verbatim_locality.isin(uncertain_keys),
            strict=True,
        )
    )

    def rests_on_link(rid: str, row: pd.Series, spec: pd.DataFrame) -> bool:
        """The flag needs an uncertain link: the specimen's own site link (W09, W11), or
        every specimen that lets the area be compared at all (W08, W10)."""
        if rid in ("W09", "W11"):
            return bool(site_uncertain.get(row.locality_id, False))
        here = spec[spec.area_id == row.locality_id]
        return len(here) > 0 and all(site_uncertain.get(x, False) for x in here.locality_id)

    def link_sensitive(rid: str, row: pd.Series) -> bool:
        other = flagged_linked[rid]
        key = "distribution_id" if "distribution_id" in row else "occurrence_id"
        return row[key] not in set(other[key])

    out = []
    for rid, (fn, kind, source) in RULES.items():
        flagged = fn(t)
        spec = _specimens(t, source)
        codes = dist[dist.locality_id.notna()]
        for _, row in flagged.iterrows():
            if rid in ("W08", "W10"):  # a Table 1 code with no specimen
                taxon, area = row.taxon_id, row.locality_id
                here = spec[spec.area_id == area]
                same_acc = here[here.taxon_id.map(acc) == acc.get(taxon)]
                prev = here[
                    here.prev_taxon_id.notna()
                    & (here.prev_taxon_id.map(acc) == acc.get(taxon))
                    & (here.taxon_id.isna() | (here.taxon_id.map(acc) != acc.get(taxon)))
                ]
                if len(same_acc):
                    cause, ev = "nomenclatural", f"{same_acc.source_ref.iloc[0]}"
                elif len(prev) and prev.taxon_id.notna().any():
                    p = prev[prev.taxon_id.notna()].iloc[0]
                    cause = "reidentified"
                    ev = f"{p.source_ref}: {p.prev_name} -> {p.verbatim_name}"
                elif len(prev):
                    p = prev.iloc[0]
                    cause, ev = "unconfirmed", f"{p.source_ref}: {p.prev_name} -> not identified"
                elif len(
                    coarse := here[
                        here.taxon_id.notna()
                        & here.taxon_id.map(rank).ne("species")
                        & (here.taxon_id.map(family) == family.get(taxon))
                    ]
                ):
                    # A specimen of the same family identified only above species level
                    # could be the voucher.
                    cause = "above_species"
                    ev = f"{coarse.source_ref.iloc[0]}: {names[coarse.taxon_id.iloc[0]]}"
                elif link_sensitive(rid, row):
                    cause, ev = "link", "flag disappears when uncertain links are linked"
                else:
                    cause, ev = "as_printed", ""
                ref = row.source_ref
            else:  # W09, W11: a specimen with no Table 1 code
                taxon, area = row.taxon_id, row.area_id
                same_area = codes[codes.locality_id == area]
                k = same_area[same_area.evidence_kind == kind]
                prev_tax = spec.loc[spec.occurrence_id == row.occurrence_id, "prev_taxon_id"]
                if rank.get(taxon) != "species":
                    cause, ev = "above_species", f"{names.get(taxon)}"
                elif (k.taxon_id.map(acc) == acc.get(taxon)).any():
                    cause, ev = "nomenclatural", ""
                elif (
                    prev_tax.notna().any()
                    and prev_tax.dropna().map(acc).isin(set(k.taxon_id.map(acc))).any()
                ):
                    p = names[prev_tax.dropna().iloc[0]]
                    cause, ev = "reidentified", f"Table 1 code under previous name {p}"
                elif link_sensitive(rid, row):
                    cause, ev = "link", "flag disappears when uncertain links are linked"
                elif (same_area.taxon_id == taxon).any():
                    other = sorted(
                        same_area.loc[same_area.taxon_id == taxon, "reference_code"]
                        .fillna(same_area.evidence_kind.map({"this_survey": "*"}))
                        .fillna("?")
                        .astype(str)
                        .unique()
                    )
                    cause, ev = "other_code", "Table 1 code(s): " + ", ".join(other)
                else:
                    cause, ev = "as_printed", ""
                ref = row.source_ref
            out.append(
                {
                    "rule": rid,
                    "source_ref": ref,
                    "taxon": names.get(taxon),
                    "area": loc_name.get(area),
                    "table1_column": area_col.get(area),
                    "cause": cause,
                    "evidence": ev,
                    "rests_on_curated_link": rests_on_link(rid, row, spec),
                }
            )
    df = pd.DataFrame(out)
    df["shift_pair"] = _shift_pairs(df)
    return df


def _shift_pairs(df: pd.DataFrame) -> list[bool]:
    """True where a code-without-specimen and a specimen-without-code for the same taxon sit
    in adjacent Table 1 columns of the same block - the signature of a column shift."""

    def adjacent(a: str | None, b: str | None) -> bool:
        if not a or not b or a[2] != b[2]:
            return False
        return abs(int(a[3:]) - int(b[3:])) == 1

    pairs = {"W08": "W09", "W09": "W08", "W10": "W11", "W11": "W10"}
    flags = []
    for _, r in df.iterrows():
        partner = df[(df.rule == pairs[r.rule]) & (df.taxon == r.taxon)]
        flags.append(any(adjacent(r.table1_column, c) for c in partner.table1_column))
    return flags


def cell_support(t: Tables) -> pd.DataFrame:
    """Taxon x area cells of Table 1 by kind of support, per region.

    The unit is the occupied cell (taxon, area), not the code: a cell often carries several
    codes. first_hand = a survey (*) or museum (a) code; literature = codes b-j.
    """
    d = t["distribution"]
    d = d[d.locality_id.notna()]
    region = dict(zip(t["locality"].locality_id, t["locality"].region, strict=True))
    rows = []
    for (taxon, area), g in d.groupby(["taxon_id", "locality_id"]):
        kinds = set(g.evidence_kind)
        refs = set(g.reference_code.dropna())
        first = bool(kinds & {"this_survey", "mohbr_collection"})
        lit = "literature" in kinds
        if first and lit:
            support = "first-hand and literature"
        elif first:
            support = "first-hand only"
        elif refs == {"e"}:
            support = "literature only: Agudo (1987) alone"
        else:
            support = "literature only: other or several sources"
        rows.append(
            {"taxon_id": taxon, "area_id": area, "region": region[area], "support": support}
        )
    return pd.DataFrame(rows)


TIERS = {
    "SurveyVouchered": "survey record with a voucher specimen of the same taxon and area",
    "SurveyUnvouchered": "survey record without a voucher in Table 2",
    "MuseumTraced": "museum record traced to a specimen in Appendix 2 (Table 3)",
    "MuseumUntraced": "museum record not traced to a specimen in Appendix 2",
    "LiteratureRecord": "record in an earlier publication, cited by the article, not consulted",
}


def evidence_tiers(t: Tables) -> pd.Series:
    """Evidence tier of every Table 1 assertion (index: distribution_id).

    A survey (*) code is vouchered when Table 2 holds a specimen of the same accepted taxon in
    the same area; a museum (a) code is traced when Table 3 holds one, under its current or
    its previous identification. Matching is by WoRMS accepted name, so a spelling variant or
    synonym does not break the link. Assertions without an area (open sea) cannot be matched.
    """
    acc = accepted_ids(t)
    d = t["distribution"]
    out = {}
    for source, kind, yes, no in (
        ("table2", "this_survey", "SurveyVouchered", "SurveyUnvouchered"),
        ("table3", "mohbr_collection", "MuseumTraced", "MuseumUntraced"),
    ):
        spec = _specimens(t, source)
        keys = set()
        for col in ("taxon_id", "prev_taxon_id"):
            ok = spec[spec[col].notna() & spec.area_id.notna()]
            keys |= set(zip(ok[col].map(acc), ok.area_id, strict=True))
        sub = d[d.evidence_kind == kind]
        for did, tax, area in zip(sub.distribution_id, sub.taxon_id, sub.locality_id, strict=True):
            out[did] = yes if (acc.get(tax), area) in keys else no
    for did in d.loc[d.evidence_kind == "literature", "distribution_id"]:
        out[did] = "LiteratureRecord"
    return pd.Series(out).reindex(d.distribution_id)


def to_markdown(review: pd.DataFrame, sens: pd.DataFrame, cells: pd.DataFrame) -> str:
    by_cause = review.groupby(["rule", "cause"]).size().unstack(fill_value=0)
    tab = pd.crosstab(cells.region, cells.support, margins=True, margins_name="all")
    out = [
        "# Cross-table review: why each W08-W11 warning fires",
        "",
        f"{len(review)} rows flagged by the four cross-source rules. Each is given one cause "
        "(the first that applies, in the order below). Printed values were confirmed by the "
        "extraction census (reports/extraction_audit.md), so no row is an extraction artefact; "
        f"{int(review.shift_pair.sum())} rows show the paired signature of a column shift.",
        "",
        "| cause | meaning |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in CAUSES.items()],
        "",
        "## Rows by rule and cause",
        "",
        by_cause.to_markdown(),
        "",
        "## Link sensitivity",
        "",
        f"The rules re-run with all {sens.attrs['uncertain_links']} curated site-to-area links "
        "that are not an exact name or a printed park name set to unlinked, as curated, and "
        "all linked (the three links the curator rejected included).",
        "",
        sens.to_markdown(index=False),
        "",
        "## Every flagged row",
        "",
        review.to_markdown(index=False),
        "",
        "## Support of Table 1 cells (taxon x area), by region",
        "",
        "Unit: occupied cell, not code. First-hand = a survey (*) or museum (a) code.",
        "",
        tab.to_markdown(),
        "",
    ]
    return "\n".join(out)
