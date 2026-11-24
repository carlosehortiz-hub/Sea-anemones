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
    elif rule_id == "C14":
        a = t["habitat_annotation"]
        a.loc[a[a.status == "negated"].index[0], "envo_id"] = "ENVO:00000316"
    return t


@pytest.mark.parametrize("rule_id", ["C01", "C06", "C07", "C09", "C10", "C11", "C12", "C13", "C14"])
def test_critical_rule_catches_injected_fault(tables, rule_id):
    assert by_id(rule_id).check(tables).empty
    assert not by_id(rule_id).check(_inject(rule_id, tables)).empty


# ------------------------------------------------------------- stage behaviour
def test_stage_fails_on_critical_but_writes_report_first(cfg, tables, monkeypatch, tmp_path):
    broken = _inject("C01", tables)
    monkeypatch.setattr(stage, "load_tables", lambda _: broken)
    monkeypatch.setattr(type(cfg), "path", lambda self, key: tmp_path)
    with pytest.raises(stage.DataQualityError, match="C01"):
        stage.validate(cfg)
    report = json.loads((tmp_path / "data_quality.json").read_text())
    assert report["status"] == "fail"
    assert "**Status: FAIL**" in (tmp_path / "data_quality.md").read_text()
