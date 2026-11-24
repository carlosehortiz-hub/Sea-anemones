"""The README's numbers are claims; check them against the generated reports and data."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from anemone_kg.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def readme(cfg):
    return (cfg.root / "README.md").read_text(encoding="utf-8")


def test_graph_and_shacl_numbers(cfg, readme):
    g = json.loads((cfg.path("reports") / "graph_summary.json").read_text())
    s = json.loads((cfg.path("reports") / "shacl_report.json").read_text())
    assert f"{g['triples']:,} triples" in readme
    assert s["conforms"]
    assert f"{s['results'].get('Warning', 0)} warnings" in readme
    assert f"{s['results'].get('Info', 0)} info" in readme
    assert f"{s['node_shapes']} node shapes" in readme


def test_data_quality_numbers(cfg, readme):
    dq = json.loads((cfg.path("reports") / "data_quality.json").read_text())
    crit = [r for r in dq["rules"] if r["severity"] == "critical"]
    warn = [r for r in dq["rules"] if r["severity"] == "warning"]
    assert f"{dq['schema_checks']} column-level checks" in readme
    assert f"{len(crit)} critical cross-table rules" in readme
    assert f"{len(warn)} warnings" in readme
    assert f"{sum(r['failing_rows'] for r in warn)} warning rows" in readme


def test_resolution_numbers(cfg, readme):
    m = pd.read_csv(cfg.path("processed") / "canonical" / "taxon_mapping.csv")
    n = m.subject_id.nunique()
    for svc, label in (("worms", "WoRMS"), ("gbif", "GBIF"), ("ncbi", "NCBI Taxonomy")):
        acc = int(((m.object_source == svc) & (m.status == "accepted")).sum())
        assert f"| {label} | {acc} / {n} |" in readme, svc
    cached = [p for p in cfg.path("cache").rglob("*.json") if "vocab" not in p.parts]
    assert f"All {len(cached)} API responses" in readme


def test_accepted_name_breakdown(cfg, readme):
    """README splits q03's rows into valid / flagged invalid / old labels / spelling only."""
    q03 = pd.read_csv(cfg.root / "queries" / "results" / "q03_accepted_name_differs.csv")
    taxa = pd.read_csv(cfg.path("processed") / "canonical" / "taxon.csv").set_index(
        "scientific_name"
    )
    ov = pd.read_csv(cfg.path("mappings") / "resolution_overrides.csv")
    spelling = set(ov.loc[ov.decision == "accept", "subject_label"]) | {"Bunodosoma cavernata"}
    spelling &= set(q03.nameInPaper)
    rest = q03[~q03.nameInPaper.isin(spelling)].nameInPaper
    old_labels = {n for n in rest if taxa.loc[n, "name_roles"] == "table3_previous"}
    invalid = {n for n in rest if bool(taxa.loc[n, "flag_invalid_in_source"])}
    valid = set(rest) - old_labels - invalid
    assert f"returns {len(q03)} names" in readme
    assert f"{len(valid)} names the paper uses as valid" in readme
    assert f"{len(invalid)} names the paper already marks as invalid" in readme
    assert f"{len(old_labels)} old collection labels" in readme
    assert f"{len(spelling)} differences in spelling only" in readme
    assert f"**{len(valid)} names" in readme
