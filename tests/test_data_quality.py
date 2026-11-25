"""Data-quality checks: each rule must *catch* the fault it exists for.

A check that never fails proves nothing, so every critical rule is tested
against a copy of the real tables with exactly one fault injected.
"""

from __future__ import annotations

import json

import pandas as pd
import pandera.pandas as pa
import pytest

from anemone_kg.config import load_config
from anemone_kg.dq.rules import RULES
from anemone_kg.dq.schemas import dataframe_schema, schema_view
from anemone_kg.stages import validate as stage


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def real(cfg):
    return stage.load_tables(cfg)


@pytest.fixture
def tables(real):
    return {k: v.copy() for k, v in real.items()}


@pytest.fixture(scope="module")
def sv(cfg):
    return schema_view(str(cfg.root / "schema" / "anemone_kg.yaml"))


def by_id(rule_id):
    return next(r for r in RULES if r.rule_id == rule_id)


# ------------------------------------------------------------------ real data
def test_real_data_passes_every_critical_check(cfg, real):
    assert stage.run_schemas(cfg, real).empty
    for r, f in stage.run_rules(real):
        if r.severity == "critical":
            assert f.empty, f"{r.rule_id}: {len(f)} rows"


def test_known_warnings_are_reported(real):
    res = {r.rule_id: len(f) for r, f in stage.run_rules(real)}
    assert res["W01"] == 1  # 31/04/2012
    assert res["W02"] == 2  # '-' localities
    assert res["W03"] == 3  # 'not identified'
    assert res["W04"] == 1  # 'In progress'


# ------------------------------------------------------- column level (Pandera)
@pytest.mark.parametrize(
    ("table", "cls", "column", "bad"),
    [
        ("occurrence", "Occurrence", "catalog_number", "1201"),  # pattern ^I-\d+$
        ("occurrence", "Occurrence", "basis_of_record", "Observation"),  # enum
        ("locality", "Locality", "decimal_latitude", 123.0),  # range
        ("taxon", "Taxon", "scientific_name", None),  # required
        ("habitat_annotation", "HabitatAnnotation", "envo_id", "ENVO:123"),  # pattern
    ],
)
def test_generated_schema_rejects(tables, sv, table, cls, column, bad):
    df = tables[table]
    df.loc[df.index[0], column] = bad
    with pytest.raises(pa.errors.SchemaErrors):
        dataframe_schema(sv, cls).validate(df, lazy=True)


def test_generated_schema_rejects_duplicate_identifier(tables, sv):
    df = pd.concat([tables["taxon"], tables["taxon"].head(1)], ignore_index=True)
    with pytest.raises(pa.errors.SchemaErrors):
        dataframe_schema(sv, "Taxon").validate(df, lazy=True)


# ------------------------------------------------------- cross-table (critical)
def _inject(rule_id, t):
    first = t["occurrence"].index[0]
    if rule_id == "C01":
        t["occurrence"].loc[first, "locality_id"] = "no-such-locality"
    elif rule_id == "C06":
        cur = t["identification"][t["identification"].is_current].head(1)
        t["identification"] = pd.concat([t["identification"], cur.assign(identification_id="x")])
    elif rule_id == "C07":
        t["occurrence"].loc[t["occurrence"].index[1], "catalog_number"] = t["occurrence"].loc[
            first, "catalog_number"
        ]
    elif rule_id == "C09":
        loc = t["locality"]
        i = loc[loc.decimal_latitude.notna()].index[0]
        loc.loc[i, "decimal_longitude"] = None
    elif rule_id == "C10":
        d = t["distribution"]
        d.loc[d[d.evidence_kind == "literature"].index[0], "is_new_record"] = True
    elif rule_id == "C11":
        m = t["taxon_mapping"]
        m.loc[m[m.status == "accepted"].index[0], "object_id"] = None
    elif rule_id == "C12":
        t["taxon_mapping"] = t["taxon_mapping"].iloc[1:]
    elif rule_id == "C13":
        w = t["worms_record"]
        t["worms_record"] = w[w.aphia_id != 283486]  # Aiptasia pallida record
    elif rule_id == "C02":
        t["identification"].loc[t["identification"].index[0], "taxon_id"] = "no-such-taxon"
    elif rule_id == "C03":
        t["distribution"].loc[t["distribution"].index[0], "reference_code"] = "z"
    elif rule_id == "C04":
        hs = t["habitat_statement"]
        hs.loc[hs.index[0], "taxon_id"] = "no-such-taxon"
    elif rule_id == "C05":
        loc = t["locality"]
        sites = loc[loc.parent_locality_id.notna()]
        loc.loc[sites.index[0], "parent_locality_id"] = sites.locality_id.iloc[1]  # a site
    elif rule_id == "C08":
        d = t["distribution"]
        t["distribution"] = pd.concat([d, d.head(1).assign(distribution_id="dup")])
    elif rule_id == "C15":
        loc = t["locality"]
        i = loc[loc.decimal_longitude.notna()].index[0]
        loc.loc[i, "decimal_longitude"] = -loc.loc[i, "decimal_longitude"]  # lost minus sign
    elif rule_id == "C14":
        a = t["habitat_annotation"]
        a.loc[a[a.status == "negated"].index[0], "envo_id"] = "ENVO:00000316"
    elif rule_id == "C16":  # a mis-keyed digit that keeps the number unique
        occ = t["occurrence"]
        i = occ[(occ.record_source == "table3") & occ.catalog_number.notna()].index[5]
        occ.loc[i, "catalog_number"] = "I-9" + occ.loc[i, "catalog_number"][2:]
    return t


CRITICAL = [r.rule_id for r in RULES if r.severity == "critical"]
WARNINGS = [r.rule_id for r in RULES if r.severity == "warning"]


@pytest.mark.parametrize("rule_id", CRITICAL)
def test_critical_rule_catches_injected_fault(tables, rule_id):
    assert by_id(rule_id).check(tables).empty
    assert not by_id(rule_id).check(_inject(rule_id, tables)).empty


def _current(t, source):
    occ = t["occurrence"]
    ids = set(occ.loc[occ.record_source == source, "occurrence_id"])
    i = t["identification"]
    return i[i.is_current & i.occurrence_id.isin(ids) & i.taxon_id.notna()]


def _inject_warning(rule_id, t):
    """One fault per warning rule; the rule must then report more rows than before.

    Bug once (found by review): W06 reported 0 rows on the real data and had no positive
    control, so '0 rows' could not be told apart from a rule that can never fire.
    """
    occ, ident, loc, m = t["occurrence"], t["identification"], t["locality"], t["taxon_mapping"]
    if rule_id == "W01":
        dated = occ[occ.event_date.notna() & occ.verbatim_event_date.notna()]
        occ.loc[dated.index[0], "occurrence_remarks"] = (
            "eventDate: impossible calendar date; published as year only"
        )
    elif rule_id == "W12":
        dated = occ[occ.event_date.fillna("").str.len().eq(10)]
        occ.loc[dated.index[0], "occurrence_remarks"] = (
            "eventDate: day given as 01, published as year-month (the day looks defaulted)"
        )
    elif rule_id == "W02":
        occ.loc[occ[occ.locality_id.notna()].index[0], "locality_id"] = None
    elif rule_id == "W03":
        ident.loc[ident[ident.is_current & ident.taxon_id.notna()].index[0], "taxon_id"] = None
    elif rule_id == "W04":
        occ.loc[occ[occ.catalog_number.notna()].index[0], "catalog_number"] = None
    elif rule_id == "W05":
        loc.loc[loc[loc.parent_locality_id.notna()].index[0], "parent_locality_id"] = None
    elif rule_id == "W06":
        taxon = m.subject_id.iloc[0]
        rows = m.subject_id == taxon
        m.loc[rows, ["status", "object_id", "predicate_id"]] = ["unresolved", None, None]
    elif rule_id == "W07":
        a = t["habitat_annotation"]
        hs = a.loc[a.status == "accepted", "habitat_statement_id"].iloc[0]
        a.loc[a.habitat_statement_id == hs, ["status", "envo_id"]] = ["rejected", None]
    elif rule_id in ("W08", "W10"):  # remove the specimens behind the codes
        source = "table2" if rule_id == "W08" else "table3"
        cur = _current(t, source)
        keep = cur.taxon_id.iloc[0]
        ident.loc[ident.occurrence_id.isin(cur[cur.taxon_id == keep].occurrence_id), "taxon_id"] = (
            t["taxon"].taxon_id.iloc[-1]
        )
    elif rule_id in ("W09", "W11"):  # re-identify a specimen as a taxon not coded there
        source = "table2" if rule_id == "W09" else "table3"
        cur = _current(t, source)
        linked = set(loc.loc[loc.parent_locality_id.notna(), "locality_id"])
        sited = set(occ.loc[occ.locality_id.isin(linked), "occurrence_id"])
        i = cur[cur.occurrence_id.isin(sited)].index[0]
        ident.loc[i, "taxon_id"] = t["taxon"].taxon_id.iloc[0]  # Scolanthus: no codes
    return t


@pytest.mark.parametrize("rule_id", WARNINGS)
def test_warning_rule_has_a_positive_control(tables, rule_id):
    before = len(by_id(rule_id).check(tables))
    after = len(by_id(rule_id).check(_inject_warning(rule_id, tables)))
    assert after > before, f"{rule_id}: {before} -> {after}"


# ------------------------------------------------------------- stage behaviour
def test_stage_fails_on_critical_but_writes_report_first(cfg, tables, monkeypatch, tmp_path):
    broken = _inject("C01", tables)
    monkeypatch.setattr(stage, "load_tables", lambda _: broken)
    real_path = type(cfg).path
    monkeypatch.setattr(
        type(cfg), "path", lambda self, key: tmp_path if key == "reports" else real_path(self, key)
    )
    with pytest.raises(stage.DataQualityError, match="C01"):
        stage.validate(cfg)
    report = json.loads((tmp_path / "data_quality.json").read_text())
    assert report["status"] == "fail"
    assert "**Status: FAIL**" in (tmp_path / "data_quality.md").read_text()
