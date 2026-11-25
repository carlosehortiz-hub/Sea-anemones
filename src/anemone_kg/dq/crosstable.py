"""Where Table 1 and the specimen tables disagree, why, and how strong each record is.

Unit. The comparison is made per *cell*: one accepted name (WoRMS) x one Table 1 area, with
both directions merged. A row-level count (the W08-W11 warnings) can describe one event twice
- a code without a specimen and the same specimen without a code - and is conditioned on areas
that the specimen table covers; the cell unit is neither.

Four kinds of discrepancy are recorded for a cell, independently:

* ``survey_code_no_voucher``: a survey code (*) and no Table 2 specimen currently identified
  as that taxon. The legend defines * as "records documented in our surveys", which does not
  require a specimen, so this kind is *expected* rather than a contradiction;
* ``museum_code_no_specimen``: a museum code (a) and no Table 3 specimen currently identified as
  that taxon. The legend refers code a to Appendix 2 (Table 3), so this is a difference between
  the article's own tables;
* ``survey_specimen_no_code`` and ``museum_specimen_no_code``: the reverse.

Causes are multi-label: every cause that applies is recorded, and the counts are marginal. A
cause *explains* a discrepancy only if it is a property of the article (re-identification,
unconfirmed identification, identification above species level, or the same presence under
another code); a dependence on a curated site-to-area link is reported separately, as a
condition, never as an explanation.

Uncertain link (one definition throughout): a curated link from a Table 3 locality to a
Table 1 area whose rule is neither an exact name match nor a printed park name (rules
``names_area``, ``article_variant`` and ``geographic_knowledge``). The analysis is re-run
with all of them unlinked and all of them linked.

Evidence tier (per Table 1 assertion) depends on traceability *and* on the identification
status of the specimen behind it: a museum code traced only through the specimen's previous
identification is not ranked with one whose current identification agrees.
"""

from __future__ import annotations

import pandas as pd

from anemone_kg.dq.rules import Tables

CERTAIN_LINK_RULES = {"exact", "park_name"}

KINDS = {
    "survey_code_no_voucher": "survey code (*) without a Table 2 specimen",
    "museum_code_no_specimen": "museum code (a) without a Table 3 specimen",
    "survey_specimen_no_code": "Table 2 specimen without a survey code (*)",
    "museum_specimen_no_code": "Table 3 specimen without a museum code (a)",
}
CAUSES = {
    "reidentified": "Table 3 re-identified the specimen; Table 1 keeps the previous name",
    "unconfirmed": "Table 3 lists the specimen as 'not identified'",
    "above_species": "identified only above species level (possible explanation)",
    "other_code": "presence agrees, but Table 1 or the other specimen table codes it otherwise",
}
CONDITIONS = {
    "link_dependent": "the discrepancy changes when uncertain links are all unlinked or linked",
    "area_without_specimens": "the specimen table has no specimen at all from this area",
}

TIERS = {
    "SurveyVouchered": "survey code with a Table 2 specimen of the same accepted taxon",
    "SurveyVoucheredQualified": "survey code whose Table 2 specimen is identified with cf./sp.",
    "SurveyUnvouchered": "survey code without a Table 2 specimen",
    "MuseumConfirmed": "museum code with a Table 3 specimen whose current identification agrees",
    "MuseumReidentified": "museum code traced only to a specimen now identified as another taxon",
    "MuseumUnconfirmed": "museum code traced only to a specimen now 'not identified'",
    "MuseumUntraced": "museum code without any Table 3 specimen",
    "LiteratureRecord": "record in an earlier publication, cited by the article, not consulted",
}
SPECIMEN_CONFIRMED = {"SurveyVouchered", "MuseumConfirmed"}
BEST_TIER = {  # Fig. 4 classes, best first
    "specimen": "specimen listed, identification confirmed",
    "code": "survey/museum code, no confirmed specimen",
    "lit_other": "literature only: other or several sources",
    "lit_agudo": "literature only: Agudo (1987) alone",
}


# ------------------------------------------------------------------------- helpers


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


def uncertain_links(crosswalk: pd.DataFrame) -> pd.DataFrame:
    """The curated Table 3 links that are neither exact names nor printed park names."""
    cw = crosswalk[crosswalk.source_table == "table3"]
    return cw[~cw.rule.isin(CERTAIN_LINK_RULES) & cw.table1_locality_col_id.notna()]


def relink(t: Tables, crosswalk: pd.DataFrame, scenario: str) -> Tables:
    """Tables with every uncertain link set to 'linked' or 'unlinked'."""
    if scenario == "as_curated":
        return t
    loc = t["locality"].copy()
    col_area = {v: k for k, v in _area_col(t).items()}
    un = uncertain_links(crosswalk)
    for key, col in zip(un.verbatim_key, un.table1_locality_col_id, strict=True):
        is_site = (loc.locality_level == "site") & (loc.verbatim_locality == key)
        loc.loc[is_site, "parent_locality_id"] = (
            col_area.get(col) if scenario == "all_linked" else None
        )
    return {**t, "locality": loc}


def _specimens(t: Tables, source: str) -> pd.DataFrame:
    """Specimens of one table with area, current taxon and qualifier, and previous taxon."""
    occ = t["occurrence"][t["occurrence"].record_source == source]
    ident = t["identification"]
    cur = ident[ident.is_current][
        ["occurrence_id", "taxon_id", "verbatim_name", "identification_qualifier"]
    ]
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


class _Evidence:
    """Codes and specimens per (accepted taxon, area) for one linking scenario."""

    def __init__(self, t: Tables, by_name: bool = False) -> None:
        # by_name: key cells on the printed name instead of the WoRMS accepted name
        self.acc = acc = {k: k for k in t["taxon"].taxon_id} if by_name else accepted_ids(t)
        self.rank = dict(zip(t["taxon"].taxon_id, t["taxon"].taxon_rank, strict=True))
        d = t["distribution"]
        d = d[d.locality_id.notna()]
        self.codes: dict[tuple, set[str]] = {}
        for tax, area, kind in zip(d.taxon_id, d.locality_id, d.evidence_kind, strict=True):
            self.codes.setdefault((acc.get(tax), area), set()).add(kind)
        self.spec = {s: _specimens(t, s) for s in ("table2", "table3")}
        self.current: dict[str, dict[tuple, pd.DataFrame]] = {}
        for s, sp in self.spec.items():
            ok = sp[sp.taxon_id.notna() & sp.area_id.notna()]
            keys = list(zip(ok.taxon_id.map(acc), ok.area_id, strict=True))
            self.current[s] = {k: ok[[kk == k for kk in keys]] for k in set(keys)}
        self.areas_with = {s: set(sp.area_id.dropna()) for s, sp in self.spec.items()}

    def kinds(self, cell: tuple) -> set[str]:
        codes = self.codes.get(cell, set())
        has2 = cell in self.current["table2"]
        has3 = cell in self.current["table3"]
        out = set()
        if "this_survey" in codes and not has2:
            out.add("survey_code_no_voucher")
        if "mohbr_collection" in codes and not has3:
            out.add("museum_code_no_specimen")
        if has2 and "this_survey" not in codes:
            out.add("survey_specimen_no_code")
        if has3 and "mohbr_collection" not in codes:
            out.add("museum_specimen_no_code")
        return out

    def cells(self) -> set[tuple]:
        return set(self.codes) | set(self.current["table2"]) | set(self.current["table3"])


# --------------------------------------------------------------------- discrepancies


def discrepancies(t: Tables, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """One row per discrepant (accepted taxon x area) cell, with kinds, causes, conditions."""
    ev = _Evidence(t)
    scen = {s: _Evidence(relink(t, crosswalk, s)) for s in ("all_unlinked", "all_linked")}
    acc_name = _accepted_names(t)
    loc_name = dict(zip(t["locality"].locality_id, t["locality"].locality_name, strict=True))
    region = dict(zip(t["locality"].locality_id, t["locality"].region, strict=True))
    tx = t["taxon"]
    family = {
        ev.acc.get(i): str(f)
        for i, f in zip(tx.taxon_id, tx.family.fillna(tx.scientific_name), strict=True)
        if ev.acc.get(i)
    }
    rows = []
    for cell in sorted(ev.cells(), key=lambda c: (acc_name.get(c[0], ""), loc_name.get(c[1], ""))):
        kinds = ev.kinds(cell)
        if not kinds:
            continue
        taxon, area = cell
        codes = ev.codes.get(cell, set())
        t3 = ev.spec["table3"]
        here3 = t3[t3.area_id == area]
        prev_hit = here3[here3.prev_taxon_id.map(ev.acc) == taxon]
        reid = prev_hit[prev_hit.taxon_id.notna() & (prev_hit.taxon_id.map(ev.acc) != taxon)]
        unconf = prev_hit[prev_hit.taxon_id.isna()]
        # the specimen side of a re-identification: its previous name carries the code
        mine = ev.current["table3"].get(cell)
        reid_spec = (
            mine is not None
            and "museum_specimen_no_code" in kinds
            and any(
                "mohbr_collection" in ev.codes.get((ev.acc.get(p), area), set())
                for p in mine.prev_taxon_id.dropna()
            )
        )
        coarse = False
        for s in ("table2", "table3"):
            sp = ev.spec[s]
            c = sp[(sp.area_id == area) & sp.taxon_id.notna()]
            c = c[c.taxon_id.map(ev.rank).ne("species")]
            if any(family.get(ev.acc.get(x)) == family.get(taxon) for x in c.taxon_id):
                coarse = True
        if ev.rank.get(_any_taxon(t, ev.acc, taxon)) not in (None, "species"):
            coarse = True
        other_code = False
        if "survey_specimen_no_code" in kinds and codes - {"this_survey"}:
            other_code = True
        if "museum_specimen_no_code" in kinds and codes - {"mohbr_collection"}:
            other_code = True
        if "museum_code_no_specimen" in kinds and cell in ev.current["table2"]:
            other_code = True  # a Table 2 voucher deposited in MOHBR, coded 'a'
        if "survey_code_no_voucher" in kinds and cell in ev.current["table3"]:
            other_code = True
        causes = {
            "reidentified": len(reid) > 0 or reid_spec,
            "unconfirmed": len(unconf) > 0,
            "above_species": coarse,
            "other_code": other_code,
        }
        link_dep = any(s.kinds(cell) != kinds for s in scen.values())
        no_specimens = (
            "survey_code_no_voucher" in kinds and area not in ev.areas_with["table2"]
        ) or ("museum_code_no_specimen" in kinds and area not in ev.areas_with["table3"])
        evidence = "; ".join(
            [f"{r.source_ref}: {r.prev_name} -> {r.verbatim_name}" for r in reid.itertuples()]
            + [f"{r.source_ref}: {r.prev_name} -> not identified" for r in unconf.itertuples()]
        )
        rows.append(
            {
                "taxon": acc_name.get(taxon, str(taxon)),
                "aphia_id": taxon,
                "area": loc_name.get(area),
                "region": region.get(area),
                **{k: k in kinds for k in KINDS},
                **causes,
                # Only properties of the article explain; the same presence under another
                # code still disagrees at code level and is reported as such.
                "explained": causes["reidentified"]
                or causes["unconfirmed"]
                or causes["above_species"],
                "code_level_only": causes["other_code"]
                and not (
                    causes["reidentified"] or causes["unconfirmed"] or causes["above_species"]
                ),
                "link_dependent": link_dep,
                "area_without_specimens": no_specimens,
                "table1_codes": ", ".join(sorted(codes)) or "-",
                "evidence": evidence,
            }
        )
    return pd.DataFrame(rows)


def _accepted_names(t: Tables) -> dict[int, str]:
    w = t["worms_record"]
    names = dict(zip(w.aphia_id.astype(int), w.scientific_name, strict=True))
    return {a: names.get(a, str(a)) for a in set(accepted_ids(t).values())}


def _any_taxon(t: Tables, acc: dict, aphia: int) -> str | None:
    return next((tx for tx, a in acc.items() if a == aphia), None)


def scenario_counts(t: Tables, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Discrepant cells by kind under the three linking scenarios."""
    rows = []
    for s in ("all_unlinked", "as_curated", "all_linked"):
        ev = _Evidence(relink(t, crosswalk, s))
        kinds = [ev.kinds(c) for c in ev.cells()]
        rows.append(
            {
                "scenario": s,
                "cells": sum(bool(k) for k in kinds),
                **{k: sum(k in ks for ks in kinds) for k in KINDS},
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["uncertain_links"] = len(uncertain_links(crosswalk))
    return df


def name_level_count(t: Tables) -> int:
    """Discrepant cells if taxa were compared by printed name instead of accepted name."""
    ev = _Evidence(t, by_name=True)
    return sum(bool(ev.kinds(c)) for c in ev.cells())


# -------------------------------------------------------------------- evidence tiers


def evidence_tiers(t: Tables) -> pd.Series:
    """Evidence tier of every Table 1 assertion (index: distribution_id)."""
    acc = accepted_ids(t)
    d = t["distribution"]
    s2, s3 = _specimens(t, "table2"), _specimens(t, "table3")
    out = {}
    for r in d.itertuples():
        a, area = acc.get(r.taxon_id), r.locality_id
        if r.evidence_kind == "literature":
            out[r.distribution_id] = "LiteratureRecord"
            continue
        if r.evidence_kind == "this_survey":
            hit = (
                s2[(s2.area_id == area) & (s2.taxon_id.map(acc) == a)] if pd.notna(area) else s2[:0]
            )
            if hit.identification_qualifier.isna().any():
                tier = "SurveyVouchered"
            elif len(hit):
                tier = "SurveyVoucheredQualified"
            else:
                tier = "SurveyUnvouchered"
        else:
            here = s3[s3.area_id == area] if pd.notna(area) else s3[:0]
            if (here.taxon_id.map(acc) == a).any():
                tier = "MuseumConfirmed"
            else:
                prev = here[here.prev_taxon_id.map(acc) == a]
                if prev.taxon_id.notna().any():
                    tier = "MuseumReidentified"
                elif len(prev):
                    tier = "MuseumUnconfirmed"
                else:
                    tier = "MuseumUntraced"
        out[r.distribution_id] = tier
    return pd.Series(out).reindex(d.distribution_id)


def supporting_specimens(t: Tables) -> dict[str, list[str]]:
    """distribution_id -> occurrenceIDs of the specimens whose current identification matches
    the assertion's accepted taxon in the same area (survey: Table 2; museum: Table 3)."""
    acc = accepted_ids(t)
    d = t["distribution"]
    out: dict[str, list[str]] = {}
    for kind, source in (("this_survey", "table2"), ("mohbr_collection", "table3")):
        sp = _specimens(t, source)
        sp = sp[sp.taxon_id.notna() & sp.area_id.notna()]
        by_key: dict[tuple, list[str]] = {}
        for oid, tx, area in zip(sp.occurrence_id, sp.taxon_id, sp.area_id, strict=True):
            by_key.setdefault((acc.get(tx), area), []).append(oid)
        sub = d[(d.evidence_kind == kind) & d.locality_id.notna()]
        for did, tx, area in zip(sub.distribution_id, sub.taxon_id, sub.locality_id, strict=True):
            hits = by_key.get((acc.get(tx), area))
            if hits:
                out[did] = sorted(hits)
    return out


def cell_support(t: Tables, by: str = "name") -> pd.DataFrame:
    """Table 1 cells (taxon x area) with kind of support and best evidence tier.

    ``by="name"`` keys cells on the name printed in Table 1 (the unit of Fig. 4 and query q07);
    ``by="accepted"`` merges names with the same WoRMS accepted name (a sensitivity analysis).
    """
    d = t["distribution"]
    d = d[d.locality_id.notna()]
    tiers = evidence_tiers(t)
    d = d.assign(tier=d.distribution_id.map(tiers))
    acc = accepted_ids(t)
    key = d.taxon_id if by == "name" else d.taxon_id.map(acc)
    loc = t["locality"].set_index("locality_id")
    rows = []
    for (taxon, area), g in d.assign(key=key).groupby(["key", "locality_id"]):
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
        if set(g.tier) & SPECIMEN_CONFIRMED:
            best = "specimen"
        elif first:
            best = "code"
        elif refs == {"e"}:
            best = "lit_agudo"
        else:
            best = "lit_other"
        rows.append(
            {
                "taxon": taxon,
                "area_id": area,
                "region": loc.region[area],
                "sampled": bool(loc.sampled_in_study[area]),
                "support": support,
                "best_tier": best,
            }
        )
    return pd.DataFrame(rows)


def tier_rule_crosstab(t: Tables) -> pd.DataFrame:
    """How the assertion tiers relate to the W08/W10 rows (which are area-conditioned)."""
    from anemone_kg.dq.rules import _w08, _w10

    tiers = evidence_tiers(t)
    w = set(_w08(t).distribution_id) | set(_w10(t).distribution_id)
    d = t["distribution"]
    d = d[d.evidence_kind != "literature"]
    spec_areas = {
        "this_survey": set(_specimens(t, "table2").area_id.dropna()),
        "mohbr_collection": set(_specimens(t, "table3").area_id.dropna()),
    }
    out = d.assign(
        tier=d.distribution_id.map(tiers),
        flagged=d.distribution_id.isin(w),
        area_has_specimens=[
            pd.notna(a) and a in spec_areas[k]
            for a, k in zip(d.locality_id, d.evidence_kind, strict=True)
        ],
    )
    return (
        out.groupby(["evidence_kind", "tier", "area_has_specimens", "flagged"])
        .size()
        .rename("assertions")
        .reset_index()
    )


# -------------------------------------------------------------------------- report


def to_markdown(disc: pd.DataFrame, scen: pd.DataFrame, cells: pd.DataFrame) -> str:
    kinds = {k: int(disc[k].sum()) for k in KINDS}
    causes = {k: int(disc[k].sum()) for k in CAUSES}
    resid = disc[~disc.explained & ~disc.code_level_only]
    tab = pd.crosstab(cells.region, cells.best_tier, margins=True, margins_name="all")
    out = [
        "# Cross-table review: Table 1 codes against the specimen tables",
        "",
        "Unit: one cell = WoRMS accepted name x Table 1 area, both directions merged, every area "
        "(not only areas from which the specimen table has specimens). Causes are multi-label; "
        "a dependence on a curated site-to-area link is a condition, not an explanation.",
        "",
        f"**{len(disc)} discrepant cells.** {int(disc.explained.sum())} are explained by the "
        "article (re-identification, unconfirmed identification, or possibly an identification "
        f"above species level); {int(disc.code_level_only.sum())} agree on presence but differ in "
        f"the code; {len(resid)} remain unexplained. {int(disc.link_dependent.sum())} change "
        f"when the {scen.attrs['uncertain_links']} uncertain links are all unlinked or all "
        "linked.",
        "",
        "| kind | cells | unexplained |",
        "|---|---:|---:|",
        *[f"| {KINDS[k]} | {kinds[k]} | {int(resid[k].sum())} |" for k in KINDS],
        "",
        "| cause (multi-label) | cells |",
        "|---|---:|",
        *[f"| {CAUSES[k]} | {causes[k]} |" for k in CAUSES],
        *[f"| condition: {CONDITIONS[k]} | {int(disc[k].sum())} |" for k in CONDITIONS],
        "",
        "## Link scenarios (discrepant cells)",
        "",
        scen.to_markdown(index=False),
        "",
        "## Every discrepant cell",
        "",
        disc.to_markdown(index=False),
        "",
        "## Best evidence tier of Table 1 cells (printed name x area), by region",
        "",
        tab.to_markdown(),
        "",
    ]
    return "\n".join(out)


def table1_cells_for(disc: pd.DataFrame, t: Tables) -> pd.DataFrame:
    """The printed Table 1 cell (row, column) behind each discrepant cell, where one exists:
    the coded cell for a code without a specimen, the empty cell for a specimen without a code.
    """
    acc = accepted_ids(t)
    taxa = t["taxon"].dropna(subset=["table1_row"])
    rows_of: dict[int, list[int]] = {}
    for tx, row in zip(taxa.taxon_id, taxa.table1_row, strict=True):
        rows_of.setdefault(acc.get(tx), []).append(int(row))
    loc = t["locality"]
    areas = loc[loc.locality_level == "area"]
    name_area = dict(zip(areas.locality_name, areas.locality_id, strict=True))
    col = _area_col(t)
    out = []
    for r in disc.itertuples():
        area = name_area.get(r.area)
        kinds = [k for k in KINDS if getattr(r, k)]
        for row in rows_of.get(r.aphia_id, []):
            out.append(
                {
                    "row_no": row,
                    "locality_col_id": col[area],
                    "label": f"Table 1 row {row}, {r.area}: {r.taxon} - "
                    + "; ".join(KINDS[k] for k in kinds),
                }
            )
    return pd.DataFrame(out)
