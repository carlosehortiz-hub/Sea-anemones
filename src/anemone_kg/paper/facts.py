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
    f["q"]["q02"] = q["q02_new_records_by_locality"].to_dict("records")
    f["q"]["q04"] = q["q04_taxa_and_specimens_by_habitat"].to_dict("records")
    f["q"]["q01"] = q["q01_species_per_order"].to_dict("records")
    f["q"]["q05"] = q["q05_provenance_of_a_record"].to_dict("records")
    changes = _csv(rep / "taxonomic_changes.csv")
    f["q"]["q03"] = _breakdown_q03(q["q03_accepted_name_differs"], tables["taxon"], ov, changes)

    f["q"]["q07"] = q["q07_cell_support_by_region"].to_dict("records")
    _revision_facts(cfg, f, tables, dq, ov, cw, cache)
    f["versions"] = {p.replace("-", "_"): version(p) for p in PACKAGES}
    f["versions"]["python"] = "3.12"
    return f


# ICZN case of each curated orthographic variant (also in the mapping justification).
SPELLING_CASE = {
    "Bunodosoma cavernata": "gender agreement (Art. 34.2)",
    "Ceriantheopsis americanus": "gender agreement (Art. 34.2)",
    "Homostichantus duerdenii": "incorrect subsequent spelling (Arts 33.3, 33.4)",
    "Palythoa caribbeorum": "incorrect subsequent spelling (Art. 33.3)",
}


def short_cite(source: str) -> str:
    """'new combination reference: Montenegro, J.; Low, M. (2015)' -> 'Montenegro et al. 2015'."""
    import re

    text = source.split(": ", 1)[-1]
    year = re.search(r"((?:17|18|19|20)\d\d)", text)
    if text.startswith("unaccept reason"):
        text = text.split(": ", 1)[-1]
    m = re.search(r"by ([A-Z][^0-9]+?) ((?:17|18|19|20)\d\d)", text)
    if m:  # "new genus created by Grajales & Rodriguez 2014"
        return f"{m.group(1).strip()} {m.group(2)}"
    authors = text.split("(")[0].strip().rstrip(".")
    names = [a.strip() for a in authors.split(";") if a.strip()]
    if len(names) == 1 and (" and " in authors or authors.count(",") >= 3):
        names = [authors, "", ""]  # "Ocaña, O, den Hartog, J. C., and Brito A." - several
    first = names[0].split(",")[0].strip().rstrip(".") if names else authors
    who = (
        first
        if len(names) == 1
        else f"{first} et al."
        if len(names) > 2
        else (f"{first} & {names[1].split(',')[0].strip()}")
    )
    return f"{who} {year.group(1)}" if year else who


def _breakdown_q03(
    q03: pd.DataFrame, taxa: pd.DataFrame, ov: pd.DataFrame, changes: pd.DataFrame
) -> dict:
    """q03 rows by the article's use of the name, with the relation and the act from WoRMS."""
    t = taxa.set_index("scientific_name")
    ch = changes.set_index("name")
    rows = []
    for r in q03.itertuples():
        name = r.nameInPaper
        if name in SPELLING_CASE:
            cat = "spelling variant"
        elif t.loc[name, "name_roles"] == "table3_previous":
            cat = "old museum label"
        elif bool(t.loc[name, "flag_invalid_in_source"]):
            cat = "† in Table 1"
        else:
            cat = "used as valid"
        if name in ch.index:
            c = ch.loc[name]
            relation = c.relation
            acts = [
                short_cite(a)
                for a in str(c.act_sources).split(" | ")
                if a and a != "nan" and not a.startswith("unaccept reason: name unavailable")
            ]
            act = ", ".join(dict.fromkeys(acts)) or "not given"
            timing = c.timing
            aphia = int(c.accepted_aphia_id)
        else:
            relation = SPELLING_CASE.get(name, "")
            act, timing, aphia = "-", "-", None
        if name in SPELLING_CASE:
            relation = "orthographic variant: " + SPELLING_CASE[name]
        rows.append(
            {
                "name": name,
                "status": r.wormsStatus,
                "accepted": r.acceptedName,
                "category": cat,
                "relation": relation,
                "act": act,
                "timing": timing,
                "aphia": aphia,
            }
        )
    c = Counter(r["category"] for r in rows)
    valid = [r for r in rows if r["category"] == "used as valid"]
    return {
        "rows": rows,
        "n": len(rows),
        "valid": c.get("used as valid", 0),
        "invalid": c.get("† in Table 1", 0),
        "label": c.get("old museum label", 0),
        "spelling": c.get("spelling variant", 0),
        "valid_changed": sum(r["status"] != "alternative representation" for r in valid),
        "valid_altrep": sum(r["status"] == "alternative representation" for r in valid),
        "valid_before_2016": sum(r["timing"] == "before 2016" for r in valid),
        "valid_undated": sum(r["timing"] == "not dated in WoRMS" for r in valid),
        "valid_mixed": sum(r["timing"] == "before and after 2016" for r in valid),
    }


def _revision_facts(cfg: Config, f: dict, tables: dict, dq: dict, ov, cw, cache) -> None:
    """Facts added in response to peer review: census, causes, cells, tiers, provenance."""
    from anemone_kg.dq import crosstable
    from anemone_kg.stages.validate import load_tables

    rep = cfg.path("reports")
    f["census"] = dq["extraction_census"]
    xt = dq["cross_table"]
    review = _csv(rep / "cross_table_review.csv")
    f["xt"] = {
        **xt,
        "rows_list": review.to_dict("records"),
        "n_by_cause": review.cause.value_counts().to_dict(),
        "explained": int((review.cause != "as_printed").sum()),
    }
    tiers = crosstable.evidence_tiers(load_tables(cfg)).value_counts().to_dict()
    f["tiers"] = tiers
    cells = pd.DataFrame(f["q"]["q07"])
    tot = cells.groupby("support").cells.sum().to_dict()
    n = int(cells.cells.sum())
    lit_only = tot.get("literature only: Agudo (1987) alone", 0) + tot.get(
        "literature only: other or several sources", 0
    )
    by_region = {}
    for region, g in cells.groupby("region"):
        d = dict(zip(g.support, g.cells, strict=True))
        rn = int(g.cells.sum())
        lo = d.get("literature only: Agudo (1987) alone", 0) + d.get(
            "literature only: other or several sources", 0
        )
        by_region[region] = {"n": rn, "lit_only": lo, "pct_lit_only": round(100 * lo / rn)}
    f["cells"] = {
        "n": n,
        "by_support": tot,
        "lit_only": lit_only,
        "pct_lit_only": round(100 * lit_only / n),
        "agudo_alone": tot.get("literature only: Agudo (1987) alone", 0),
        "pct_agudo_alone": round(100 * tot.get("literature only: Agudo (1987) alone", 0) / n),
        "first_hand": tot.get("first-hand only", 0) + tot.get("first-hand and literature", 0),
        "by_region": by_region,
    }
    d = tables["distribution"]
    lit = d[d.evidence_kind == "literature"]
    f["codes"] = {
        "literature": len(lit),
        "agudo": int((lit.reference_code == "e").sum()),
        "pct_agudo_of_literature": round(100 * (lit.reference_code == "e").mean()),
        "survey": int((d.evidence_kind == "this_survey").sum()),
        "mohbr": int((d.evidence_kind == "mohbr_collection").sum()),
    }
    cov = _csv(rep / "ncbi_coverage.csv")
    un = cov[cov.taxid.isna()]
    linked = cov[cov.taxid.notna()]
    f["ncbi_cov"] = {
        "unresolved": len(un),
        "recovered": un.loc[un.retry_hit != "none", ["name", "retry_hit"]].to_dict("records"),
        "n_recovered": int((un.retry_hit != "none").sum()),
        "genus_absent": int((un.genus_in_ncbi == False).sum()),  # noqa: E712
        "linked": len(linked),
        "linked_zero": int((linked.nucleotide_records == 0).sum()),
        "linked_le10": int((linked.nucleotide_records <= 10).sum()),
        "median_records": int(linked.nucleotide_records.median()),
        "by_order": cov.assign(ok=cov.taxid.notna())
        .groupby(cov.order.fillna("name variant"))
        .ok.agg(["sum", "count"])
        .astype(int)
        .to_dict(orient="index"),
    }
    prov = json.loads((rep / "taxonomic_provenance.json").read_text())
    f["prov"] = prov
    taxa = tables["taxon"]
    roles = taxa.name_roles.fillna("")
    f["names"] = {
        "table1": int(roles.str.contains("table1").sum()),
        "table2_only": int((roles == "table2").sum()),
        "table3_previous": int((roles == "table3_previous").sum()),
    }
    m = tables["taxon_mapping"]
    w = tables["worms_record"]
    matched = set(
        m[(m.object_source == "worms") & m.object_id.notna()]
        .object_id.str.split(":")
        .str[1]
        .astype(int)
    )
    f["worms_nodes"] = {"matched": len(matched), "accepted_only": len(set(w.aphia_id) - matched)}
    loc = tables["locality"]
    sites = loc[loc.locality_level == "site"]
    t3 = cw[cw.source_table == "table3"]
    f["loc"] = {
        "columns": f["src"]["t1_localities"],
        "areas": int((loc.locality_level == "area").sum()),
        "sites": len(sites),
        "sites_linked": int(sites.parent_locality_id.notna().sum()),
        "sites_unlinked": int(sites.parent_locality_id.isna().sum()),
        "crosswalk_rows": len(cw),
        "crosswalk_parks": int((cw.source_table == "table2").sum()),
        "crosswalk_t3_linked": int(
            ((t3.status == "accepted") & t3.table1_locality_col_id.notna()).sum()
        ),
        "crosswalk_t3_nomatch": int((t3.rule == "no_match").sum()),
        "crosswalk_t3_rejected": int((t3.status == "rejected").sum()),
        "areas_with_coords": int(
            loc[(loc.locality_level == "site") & loc.decimal_latitude.notna()]
            .parent_locality_id.dropna()
            .nunique()
        ),
    }
    curated = {
        n: len(_csv(cfg.path("mappings") / f"{n}.csv"))
        for n in (
            "name_variants",
            "state_names",
            "locality_crosswalk",
            "event_dates",
            "resolution_overrides",
            "habitat_vocabulary",
        )
    }
    f["curated_by_file"] = curated
    g = json.loads((rep / "graph_summary.json").read_text())
    f["graph"]["derived_by_class"] = g["derived_by_class"]
    f["graph"]["derivations"] = g["derivations"]
    sh = json.loads((rep / "shacl_report.json").read_text())
    f["shacl"]["strict"] = sh["conforms_strict"]
    f["shacl"]["by_message"] = sh["by_message"]
    cr = prov["cached_responses"]
    f["res"]["cache_purpose"] = {
        "resolution": cr["resolution"],
        "coverage": cr["coverage_and_releases"],
    }
    f["recon"] = _reconciliation(f)


def _reconciliation(f: dict) -> list[dict]:
    """One row per published count that a reader cannot rebuild from the text alone."""
    s, c, r, d, g = f["src"], f["canon"], f["res"], f["dq"], f["graph"]
    dc = g["derived_by_class"]
    loc, nm, wn, cb = f["loc"], f["names"], f["worms_nodes"], f["curated_by_file"]
    msgs = {m["message"]: m["count"] for m in f["shacl"]["by_message"]}
    ev = next(v for k, v in msgs.items() if "Event without" in k)
    return [
        {
            "count": f"{r['n_taxa']} names vs {s['t1_taxa']} Table 1 taxa",
            "derivation": f"{nm['table1']} Table 1 names + {nm['table2_only']} family-level "
            f"name in Table 2 + {nm['table3_previous']} previous identifications in Table 3",
        },
        {
            "count": f"{s['t1_localities']} localities vs {loc['areas']} areas",
            "derivation": f"{loc['columns']} Table 1 columns = {loc['areas']} areas + 1 'Open Sea "
            "Distribution' column, which is not a place (its 2 assertions have no location)",
        },
        {
            "count": f"{loc['sites']} sites",
            "derivation": f"{loc['sites_linked']} linked to a Table 1 area + "
            f"{loc['sites_unlinked']} unlinked (W05): "
            f"{loc['crosswalk_t3_rejected']} links the curator rejected + "
            f"{loc['crosswalk_t3_nomatch']} site with no Table 1 column",
        },
        {
            "count": f"{loc['crosswalk_rows']} crosswalk rows",
            "derivation": f"{loc['crosswalk_parks']} Table 2 park names + "
            f"{loc['crosswalk_t3_linked']} Table 3 localities linked + "
            f"{loc['crosswalk_t3_nomatch']} with no column + "
            f"{loc['crosswalk_t3_rejected']} rejected",
        },
        {
            "count": f"{c['curated_rows']} curated rows",
            "derivation": " + ".join(f"{v} {k.replace('_', ' ')}" for k, v in cb.items()),
        },
        {
            "count": f"{f['graph']['cls']['dwc:Taxon']} taxon nodes",
            "derivation": f"{r['n_taxa']} name usages + {r['worms_records']} WoRMS records "
            f"({wn['matched']} matched by a name + {wn['accepted_only']} accepted names only)",
        },
        {
            "count": f"{g['derivations']} qualified derivations",
            "derivation": " + ".join(
                f"{v} {k}" for k, v in sorted(dc.items(), key=lambda x: -x[1])
            ),
        },
        {
            "count": f"{s['t1_codes']} codes vs {c['distribution']} assertions",
            "derivation": f"{c['n_folded']} 'N' codes qualify a survey code and are folded "
            "into it; "
            f"{c['distribution']} - 2 open-sea = {c['distribution'] - 2} assertions with an area",
        },
        {
            "count": f"{s['t1_cells']} occupied cells vs {f['cells']['n']} cells with an area",
            "derivation": f"{s['t1_cells']} - 2 open-sea cells",
        },
        {
            "count": f"{f['shacl']['warning']} SHACL warnings + {f['shacl']['info']} info",
            "derivation": f"results per focus node: {ev} events without location (W02: 2 "
            "specimens; 2 open-sea assertions), 3 'not identified' (W03), 2 habitat statements "
            "(W07), 1 specimen without catalogue number (Info; W04). The other warning rules "
            "(W01, W05, W08-W11) have no SHACL counterpart",
        },
        {
            "count": f"{d['warning_rows']} warning rows",
            "derivation": " + ".join(
                f"{k} {v}" for k, v in d["by_id"].items() if k.startswith("W") and v
            ),
        },
        {
            "count": f"{r['cached']} cached API responses",
            "derivation": f"{r['cache_purpose'].get('resolution', 0)} for name and habitat "
            f"resolution + {r['cache_purpose'].get('coverage', 0)} for the coverage and release "
            "analyses added in revision; by service: "
            + ", ".join(f"{k} {v}" for k, v in sorted(r["cached_by_service"].items())),
        },
        {
            "count": "three different sets of four",
            "derivation": f"{c['typos']} misspelt names in Table 2 (name variants); "
            f"{r['worms']['curated']} WoRMS links accepted after curation; "
            f"{f['q']['q03']['spelling']} spelling-only rows of Table 4",
        },
    ]
