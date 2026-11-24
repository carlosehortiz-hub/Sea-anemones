"""Cross-table data-quality rules.

Each rule returns the *failing rows* (an empty frame means pass), so the
report can show exactly what is wrong, not just a count.

Severity
--------
critical  The canonical model is internally broken (dangling reference,
          duplicate identifier, contradictory flags). The pipeline stops
          before RDF generation, because a graph built on it would be wrong.
warning   The data are consistent but incomplete or disagree between sources
          in a way the paper itself explains or cannot settle (e.g. a '*'
          survey record without a voucher specimen: '*' also covers
          observations). Reported with the rows, never "fixed".

Dimensions follow the usual data-quality vocabulary: completeness,
validity, uniqueness, consistency (within and across sources).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

Tables = dict[str, pd.DataFrame]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str  # critical | warning
    dimension: str  # completeness | validity | uniqueness | consistency
    description: str
    check: Callable[[Tables], pd.DataFrame]


RULES: list[Rule] = []


def rule(rule_id: str, severity: str, dimension: str, description: str):
    def register(fn: Callable[[Tables], pd.DataFrame]) -> Callable[[Tables], pd.DataFrame]:
        RULES.append(Rule(rule_id, severity, dimension, description, fn))
        return fn

    return register


def _dangling(t: Tables, table: str, col: str, ref: str, ref_col: str) -> pd.DataFrame:
    df = t[table]
    vals = df[col]
    return df[vals.notna() & ~vals.isin(set(t[ref][ref_col]))]


# ---------------------------------------------------------------- critical
@rule("C01", "critical", "consistency", "occurrence.locality_id references an existing locality")
def _c01(t):
    return _dangling(t, "occurrence", "locality_id", "locality", "locality_id")


@rule(
    "C02", "critical", "consistency", "identification references an existing occurrence and taxon"
)
def _c02(t):
    return pd.concat(
        [
            _dangling(t, "identification", "occurrence_id", "occurrence", "occurrence_id"),
            _dangling(t, "identification", "taxon_id", "taxon", "taxon_id"),
        ]
    )


@rule(
    "C03",
    "critical",
    "consistency",
    "distribution references an existing taxon, locality and reference",
)
def _c03(t):
    return pd.concat(
        [
            _dangling(t, "distribution", "taxon_id", "taxon", "taxon_id"),
            _dangling(t, "distribution", "locality_id", "locality", "locality_id"),
            _dangling(t, "distribution", "reference_code", "reference", "reference_code"),
        ]
    )


@rule(
    "C04",
    "critical",
    "consistency",
    "taxon_name_variant, habitat_statement and taxon_mapping reference an existing taxon",
)
def _c04(t):
    return pd.concat(
        [
            _dangling(t, "taxon_name_variant", "taxon_id", "taxon", "taxon_id"),
            _dangling(t, "habitat_statement", "taxon_id", "taxon", "taxon_id"),
            _dangling(t, "taxon_mapping", "subject_id", "taxon", "taxon_id"),
        ]
    )


@rule("C05", "critical", "consistency", "a site's parent is an existing locality of level 'area'")
def _c05(t):
    loc = t["locality"]
    areas = set(loc.loc[loc.locality_level == "area", "locality_id"])
    p = loc.parent_locality_id
    return loc[p.notna() & ~p.isin(areas)]


@rule("C06", "critical", "uniqueness", "every occurrence has exactly one current identification")
def _c06(t):
    ident = t["identification"]
    n = ident[ident.is_current].groupby("occurrence_id").size()
    occ = t["occurrence"]
    occ = occ.assign(n_current=occ.occurrence_id.map(n).fillna(0).astype(int))
    return occ[occ.n_current != 1]


@rule(
    "C07",
    "critical",
    "uniqueness",
    "no duplicate specimens: catalogue numbers and field codes are unique",
)
def _c07(t):
    occ = t["occurrence"]
    out = []
    for col in ("catalog_number", "other_catalog_numbers"):
        v = occ[col]
        out.append(occ[v.notna() & v.duplicated(keep=False)])
    return pd.concat(out)


@rule(
    "C08",
    "critical",
    "uniqueness",
    "no duplicate Table 1 assertions (taxon, area, evidence, reference)",
)
def _c08(t):
    d = t["distribution"]
    key = ["taxon_id", "locality_id", "evidence_kind", "reference_code", "occurrence_remarks"]
    return d[d.duplicated(subset=key, keep=False)]


@rule("C09", "critical", "validity", "coordinates are given as a pair or not at all")
def _c09(t):
    loc = t["locality"]
    return loc[loc.decimal_latitude.isna() != loc.decimal_longitude.isna()]


@rule("C10", "critical", "consistency", "new records ('N') are only set on this-survey assertions")
def _c10(t):
    d = t["distribution"]
    return d[d.is_new_record & (d.evidence_kind != "this_survey")]


@rule(
    "C11",
    "critical",
    "consistency",
    "a mapping asserts an identifier and predicate if and only if it is accepted",
)
def _c11(t):
    m = t["taxon_mapping"]
    acc = m.status == "accepted"
    has = m.object_id.notna() & m.predicate_id.notna()
    return m[acc != has]


@rule(
    "C12",
    "critical",
    "consistency",
    "every taxon has exactly one mapping row per service (gaps are explicit)",
)
def _c12(t):
    m = t["taxon_mapping"]
    n = m.groupby(["subject_id", "object_source"]).size().unstack(fill_value=0)
    bad = n[(n != 1).any(axis=1)].index
    missing = set(t["taxon"].taxon_id) - set(m.subject_id)
    return t["taxon"][t["taxon"].taxon_id.isin(set(bad) | missing)]


@rule(
    "C13",
    "critical",
    "consistency",
    "WoRMS identifiers and their accepted-name pointers resolve to stored WoRMS records",
)
def _c13(t):
    m, w = t["taxon_mapping"], t["worms_record"]
    ids = set(w.aphia_id.astype(int))
    acc = m[(m.object_source == "worms") & m.object_id.notna()]
    bad_m = acc[~acc.object_id.str.split(":").str[1].astype(int).isin(ids)]
    bad_w = w[w.valid_aphia_id.notna() & ~w.valid_aphia_id.astype("Int64").isin(ids)]
    return pd.concat([bad_m, bad_w])


@rule(
    "C14",
    "critical",
    "consistency",
    "habitat annotations carry an ENVO id if and only if accepted, on an existing statement",
)
def _c14(t):
    a = t["habitat_annotation"]
    bad = a[(a.status == "accepted") != a.envo_id.notna()]
    return pd.concat(
        [
            bad,
            _dangling(
                t,
                "habitat_annotation",
                "habitat_statement_id",
                "habitat_statement",
                "habitat_statement_id",
            ),
        ]
    )


# ----------------------------------------------------------------- warnings
@rule("W01", "warning", "validity", "verbatim date that is not a valid calendar date")
def _w01(t):
    o = t["occurrence"]
    return o[o.verbatim_event_date.notna() & o.event_date.isna()]


@rule("W02", "warning", "completeness", "occurrence without locality ('-' in the source)")
def _w02(t):
    o = t["occurrence"]
    return o[o.locality_id.isna()]


@rule("W03", "warning", "completeness", "specimen whose current identification has no taxon")
def _w03(t):
    i = t["identification"]
    return i[i.is_current & i.taxon_id.isna()]


@rule("W04", "warning", "completeness", "specimen without a MOHBR catalogue number")
def _w04(t):
    o = t["occurrence"]
    return o[o.catalog_number.isna()]


@rule("W05", "warning", "completeness", "collecting site not linked to a Table 1 area")
def _w05(t):
    loc = t["locality"]
    return loc[(loc.locality_level == "site") & loc.parent_locality_id.isna()]


@rule("W06", "warning", "completeness", "taxon with no accepted identifier in any service")
def _w06(t):
    m = t["taxon_mapping"]
    ok = set(m.loc[m.status == "accepted", "subject_id"])
    return t["taxon"][~t["taxon"].taxon_id.isin(ok)]


@rule("W07", "warning", "completeness", "habitat statement with no ENVO annotation")
def _w07(t):
    a = t["habitat_annotation"]
    ok = set(a.loc[a.status == "accepted", "habitat_statement_id"])
    hs = t["habitat_statement"]
    return hs[~hs.habitat_statement_id.isin(ok)]


def _specimen_areas(t: Tables, source: str) -> pd.DataFrame:
    """(taxon_id, area_id, occurrence) for specimens of one table, current identification."""
    occ = t["occurrence"]
    occ = occ[occ.record_source == source]
    ident = t["identification"]
    cur = ident[ident.is_current & ident.taxon_id.notna()][["occurrence_id", "taxon_id"]]
    loc = t["locality"][["locality_id", "parent_locality_id"]]
    j = occ.merge(cur, on="occurrence_id").merge(loc, on="locality_id", how="left")
    return j.rename(columns={"parent_locality_id": "area_id"})


def _assertions(t: Tables, kind: str) -> pd.DataFrame:
    d = t["distribution"]
    return d[(d.evidence_kind == kind) & d.locality_id.notna()]


def _cross(t: Tables, kind: str, source: str, direction: str) -> pd.DataFrame:
    spec = _specimen_areas(t, source)
    spec_keys = set(zip(spec.taxon_id, spec.area_id, strict=True))
    asr = _assertions(t, kind)
    asr_keys = set(zip(asr.taxon_id, asr.locality_id, strict=True))
    if direction == "assertion_without_specimen":
        # Only areas the specimen table can speak for (some specimen exists there).
        areas = set(spec.area_id.dropna())
        mask = [
            (k not in spec_keys) and (k[1] in areas)
            for k in zip(asr.taxon_id, asr.locality_id, strict=True)
        ]
        return asr[mask]
    linked = spec[spec.area_id.notna()]
    mask = [k not in asr_keys for k in zip(linked.taxon_id, linked.area_id, strict=True)]
    return linked[mask].drop_duplicates(["taxon_id", "area_id"])


@rule(
    "W08",
    "warning",
    "consistency",
    "Table 1 '*' (this survey) in a sampled area, but no Table 2 specimen of that taxon there",
)
def _w08(t):
    return _cross(t, "this_survey", "table2", "assertion_without_specimen")


@rule(
    "W09",
    "warning",
    "consistency",
    "Table 2 specimen in an area, but no Table 1 '*' for that taxon and area",
)
def _w09(t):
    return _cross(t, "this_survey", "table2", "specimen_without_assertion")


@rule(
    "W10",
    "warning",
    "consistency",
    "Table 1 'a' (MOHBR) in an area, but no Table 3 specimen of that taxon there",
)
def _w10(t):
    return _cross(t, "mohbr_collection", "table3", "assertion_without_specimen")


@rule(
    "W11",
    "warning",
    "consistency",
    "Table 3 specimen in an area, but no Table 1 'a' for that taxon and area",
)
def _w11(t):
    return _cross(t, "mohbr_collection", "table3", "specimen_without_assertion")


def completeness(t: Tables) -> pd.DataFrame:
    rows = []
    for name, df in t.items():
        for col in df.columns:
            rows.append(
                {
                    "table": name,
                    "column": col,
                    "rows": len(df),
                    "non_null": int(df[col].notna().sum()),
                    "pct": round(100 * df[col].notna().mean(), 1) if len(df) else 100.0,
                }
            )
    return pd.DataFrame(rows)
