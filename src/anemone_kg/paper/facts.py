"""Every number the manuscript states, computed from the pipeline's outputs.

The manuscript template never contains a hand-typed result: it reads `facts`.
If the pipeline changes, rebuilding the manuscript changes the text with it.
"""

from __future__ import annotations

import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from anemone_kg.config import Config

PACKAGES = (
    "pdfplumber",
    "pandas",
    "pandera",
    "linkml-runtime",
    "rdflib",
    "pyshacl",
    "duckdb",
    "pyoxigraph",
    "requests",
)


def _csv(p: Path) -> pd.DataFrame:
    return pd.read_csv(p)


def collect(cfg: Config) -> dict:
    root, canon = cfg.root, cfg.path("processed") / "canonical"
    rep, interim, qres = cfg.path("reports"), cfg.path("interim"), root / "queries" / "results"
    f: dict = {}

    # ---------------------------------------------------------- the source
    t1 = _csv(interim / "table1_taxa.csv")
    cells = _csv(interim / "table1_cells.csv")
    locs = _csv(interim / "table1_localities.csv")
    legend = _csv(interim / "table1_legend.csv")
    f["src"] = {
        "t1_taxa": len(t1),
        "t1_localities": len(locs),
        "t1_sampled": int(locs.sampled_in_study.sum()),
        "t1_codes": len(cells),
        "t1_cells": cells.groupby(["row_no", "locality_col_id"]).ngroups,
        "t1_sources": int((legend.kind == "source").sum()),
        "t1_agudo": int((cells.code == "e").sum()),
        "t2": len(_csv(interim / "table2_specimens.csv")),
        "t3": len(_csv(interim / "table3_mohbr_specimens.csv")),
        "accounts": len(_csv(interim / "species_accounts.csv")),
        "pages": 35,
    }

    # ----------------------------------------------------- canonical model
    tables = {p.stem: _csv(p) for p in sorted(canon.glob("*.csv"))}
    f["canon"] = {k: len(v) for k, v in tables.items()}
    ident = tables["identification"]
    f["canon"]["superseded"] = int((~ident.is_current).sum())
    occ = tables["occurrence"]
    f["canon"]["t2_dated"] = int(((occ.record_source == "table2") & occ.event_date.notna()).sum())
    loc = tables["locality"]
    f["canon"]["areas"] = int((loc.locality_level == "area").sum())
    f["canon"]["sites"] = int((loc.locality_level == "site").sum())
    f["canon"]["sites_with_coords"] = int(loc.decimal_latitude.notna().sum())
    mapping = _csv(cfg.path("mappings") / "source_to_canonical.csv")
    f["canon"]["mapping_rows"] = len(mapping)
    f["canon"]["rules"] = mapping.rule_id.nunique()
    nv = _csv(cfg.path("mappings") / "name_variants.csv")
    cw = _csv(cfg.path("mappings") / "locality_crosswalk.csv")
    f["canon"]["typos"] = len(nv)
    curated = [
        "name_variants",
        "state_names",
        "locality_crosswalk",
        "event_dates",
        "resolution_overrides",
        "habitat_vocabulary",
    ]
    f["canon"]["curated_files"] = len(curated)
    f["canon"]["curated_rows"] = sum(len(_csv(cfg.path("mappings") / f"{n}.csv")) for n in curated)
    f["canon"]["crosswalk_accepted"] = int((cw.status == "accepted").sum())
    f["canon"]["crosswalk_rejected"] = int((cw.status == "rejected").sum())
    dist_in = len(cells)
    f["canon"]["n_folded"] = dist_in - len(tables["distribution"])

    # ---------------------------------------------------------- resolution
    m = tables["taxon_mapping"]
    n_taxa = m.subject_id.nunique()
    res = {"n_taxa": n_taxa, "rows": len(m)}
    for s in ("worms", "gbif", "ncbi"):
        sm = m[m.object_source == s]
        acc = sm[sm.status == "accepted"]
        res[s] = {
            "accepted": len(acc),
            "unresolved": int((sm.status == "unresolved").sum()),
            "curated": int((acc.mapping_justification == "semapv:ManualMappingCuration").sum()),
            "exact_synonym": int((acc.match_type == "exact_synonym").sum()),
            "via_accepted": int((acc.match_type == "via_accepted_name").sum()),
        }
    com = m[m.object_source == "worms"].comment.fillna("")
    res["homonyms_by_authority"] = int(com.str.contains("resolved by authority").sum())
    res["homonyms_total"] = int(com.str.contains("homonym").sum())
    ov = _csv(cfg.path("mappings") / "resolution_overrides.csv")
    res["overrides"] = len(ov)
    res["overrides_accept"] = int((ov.decision == "accept").sum())
    res["overrides_reject"] = int((ov.decision == "reject").sum())
    cache = [p for p in cfg.path("cache").rglob("*.json") if "vocab" not in p.parts]
    res["cached"] = len(cache)
    res["cached_by_service"] = dict(Counter(p.parent.name for p in cache))
    dates = sorted(json.loads(p.read_text())["retrieved_at"][:10] for p in cache)
    res["date_first"], res["date_last"] = dates[0], dates[-1]
    res["worms_records"] = len(tables["worms_record"])
    f["res"] = res

    ann = tables["habitat_annotation"]
    good = ann[ann.status == "accepted"]
    vocab = _csv(cfg.path("mappings") / "habitat_vocabulary.csv")
    f["envo"] = {
        "vocab": len(vocab),
        "matches": len(ann),
        "accepted": len(good),
        "negated": int((ann.status == "negated").sum()),
        "unresolved_labels": sorted(ann.loc[ann.status == "unresolved", "envo_label"].unique()),
        "terms": good.envo_id.nunique(),
        "statements": good.habitat_statement_id.nunique(),
        "statements_total": len(tables["habitat_statement"]),
        "rubble_statements": ann.loc[
            ann.envo_label == "coral rubble", "habitat_statement_id"
        ].nunique(),
    }
    t3 = _csv(interim / "table3_mohbr_specimens.csv")
    f["src"]["t3_missing_state"] = int(t3.verbatim_state.isna().sum())

    # ---------------------------------------------------- quality & graph
    dq = json.loads((rep / "data_quality.json").read_text())
    crit = [r for r in dq["rules"] if r["severity"] == "critical"]
    warn = [r for r in dq["rules"] if r["severity"] == "warning"]
    f["dq"] = {
        "status": dq["status"],
        "schema_checks": dq["schema_checks"],
        "n_critical": len(crit),
        "critical_failing": sum(r["failing_rows"] for r in crit),
        "n_warning": len(warn),
        "warning_rows": sum(r["failing_rows"] for r in warn),
        "warning_rules_firing": sum(1 for r in warn if r["failing_rows"]),
        "by_id": {r["id"]: r["failing_rows"] for r in dq["rules"]},
        "desc": {r["id"]: r["description"] for r in dq["rules"]},
    }
    g = json.loads((rep / "graph_summary.json").read_text())
    f["graph"] = {
        "triples": g["triples"],
        "subjects": g["subjects"],
        "cls": g["instances_per_class"],
    }
    s = json.loads((rep / "shacl_report.json").read_text())
    f["shacl"] = {
        "conforms": s["conforms"],
        "shapes": s["node_shapes"],
        "violation": s["results"].get("Violation", 0),
        "warning": s["results"].get("Warning", 0),
        "info": s["results"].get("Info", 0),
    }
    import yaml

    terms = yaml.safe_load((root / "model" / "terms.yaml").read_text())["terms"]
    f["terms"] = {
        "total": len(terms),
        "akv": sum(t["term"].startswith("akv:") for t in terms),
        "by_prefix": dict(Counter(t["term"].split(":")[0] for t in terms)),
    }

    # --------------------------------------------------------------- queries
    q = {p.stem: _csv(p) for p in sorted(qres.glob("*.csv"))}
    f["q"] = {
        "n_sparql": sum(1 for k in q if k.startswith("q")),
        "n_sql": sum(1 for k in q if k.startswith("s")),
        "rows": {k: len(v) for k, v in q.items()},
    }
    f["q"]["q07"] = q["q07_records_by_region_and_evidence"].to_dict("records")
    f["q"]["q02"] = q["q02_new_records_by_locality"].to_dict("records")
    f["q"]["q04"] = q["q04_taxa_and_specimens_by_habitat"].to_dict("records")
    f["q"]["q01"] = q["q01_species_per_order"].to_dict("records")
    f["q"]["q05"] = q["q05_provenance_of_a_record"].to_dict("records")
    f["q"]["q03"] = _breakdown_q03(q["q03_accepted_name_differs"], tables["taxon"], ov)

    f["versions"] = {p.replace("-", "_"): version(p) for p in PACKAGES}
    f["versions"]["python"] = "3.12"
    return f


def _breakdown_q03(q03: pd.DataFrame, taxa: pd.DataFrame, ov: pd.DataFrame) -> dict:
    """Split q03 rows into: valid in paper / marked invalid / old label / spelling only."""
    t = taxa.set_index("scientific_name")
    spelling = set(ov.loc[ov.decision == "accept", "subject_label"]) | {"Bunodosoma cavernata"}
    spelling &= set(q03.nameInPaper)
    rows = []
    for r in q03.itertuples():
        name = r.nameInPaper
        if name in spelling:
            cat = "spelling"
        elif t.loc[name, "name_roles"] == "table3_previous":
            cat = "label"
        elif bool(t.loc[name, "flag_invalid_in_source"]):
            cat = "invalid"
        else:
            cat = "valid"
        rows.append(
            {"name": name, "status": r.wormsStatus, "accepted": r.acceptedName, "category": cat}
        )
    c = Counter(r["category"] for r in rows)
    return {
        "rows": rows,
        "n": len(rows),
        **{k: c.get(k, 0) for k in ("valid", "invalid", "label", "spelling")},
    }
