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
        "taxonomic_acts",
    ]
    f["canon"]["curated_files"] = len(curated)
    f["canon"]["curated_rows"] = sum(len(_csv(cfg.path("mappings") / f"{n}.csv")) for n in curated)
    f["canon"]["curated_by_file"] = {
        n: len(_csv(cfg.path("mappings") / f"{n}.csv")) for n in curated
    }
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
    variants = set(
        m[
            (m.object_source == "worms")
            & (m.mapping_justification == "semapv:ManualMappingCuration")
            & (m.match_type == "fuzzy")
        ].subject_id
    )
    nc = m[(m.object_source == "ncbi") & (m.match_type == "via_accepted_name")]
    res["ncbi"]["via_variant"] = int(nc.subject_id.isin(variants).sum())
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
    f["submitted_date"] = SUBMITTED_DATE
    f["q"]["q03"] = _breakdown_q03(
        q["q03_accepted_name_differs"],
        tables["taxon"],
        _csv(cfg.path("mappings") / "taxonomic_acts.csv"),
        tables["taxon_mapping"],
        tables["worms_record"],
    )

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


SUBMITTED = 2016  # the article was received on 9 February 2016 (p. 33 of the PDF)
SUBMITTED_DATE = "9 February 2016"


def _breakdown_q03(
    q03: pd.DataFrame,
    taxa: pd.DataFrame,
    acts: pd.DataFrame,
    mapping: pd.DataFrame,
    worms: pd.DataFrame,
) -> dict:
    """q03 rows by the article's use of the name, with the relation and the act that fixes the
    current accepted name (mappings/taxonomic_acts.csv, curated after the round-3 review).

    Bug once (round 3): the column listed the sources WoRMS cites, and "timing" asked whether
    any of them predated submission. Some are not acts (a morphology paper), some fix only an
    earlier step (a genus created, not the synonymy), and two names are fixed by acts made
    after submission, so "the article lagged" did not follow. Timing now refers to the act that
    fixes today's name; a mandatory change (spelling, gender) needs no act.
    """
    t = taxa.set_index("scientific_name")
    a = acts.set_index("name")
    missing = set(q03.nameInPaper) - set(a.index)
    if missing:
        raise ValueError(f"taxonomic_acts.csv lacks rows for {sorted(missing)}")
    wm = mapping[(mapping.object_source == "worms") & mapping.object_id.notna()]
    valid_of = dict(zip(worms.aphia_id.astype(int), worms.valid_aphia_id, strict=True))
    aphia_of = {}
    for name, oid in zip(wm.subject_label, wm.object_id, strict=True):
        aid = int(oid.split(":")[1])
        v = valid_of.get(aid)
        aphia_of[name] = int(v) if pd.notna(v) else aid
    rows = []
    for r in q03.itertuples():
        name = r.nameInPaper
        c = a.loc[name]
        if name in SPELLING_CASE:
            cat = "spelling variant"
        elif t.loc[name, "name_roles"] == "table3_previous":
            cat = "previous museum identification"
        elif bool(t.loc[name, "flag_invalid_in_source"]):
            cat = "† in Table 1"
        else:
            cat = "used as valid"
        fixing = str(c.fixing_act)
        if fixing == "mandatory":
            timing = "mandatory change, no act"
        elif fixing in ("not cited", "not identified"):
            timing = f"act {fixing}"
        elif int(c.fixing_year) < SUBMITTED:
            timing = "act before submission"
        else:
            timing = "act after submission"
        rows.append(
            {
                "name": name,
                "status": r.wormsStatus,
                "accepted": r.acceptedName,
                "category": cat,
                "relation": c.relation,
                "act_keys": [k for k in str(c.acts).split(";") if k and k != "nan"],
                "fixing_act": fixing,
                "timing": timing,
                "concept": c.concept_status,
                "aphia": aphia_of.get(name),
            }
        )
    cat = Counter(r["category"] for r in rows)
    tim = Counter(r["timing"] for r in rows)
    con = Counter(r["concept"] for r in rows)
    valid = [r for r in rows if r["category"] == "used as valid"]
    return {
        "rows": rows,
        "n": len(rows),
        "valid": cat.get("used as valid", 0),
        "invalid": cat.get("† in Table 1", 0),
        "label": cat.get("previous museum identification", 0),
        "spelling": cat.get("spelling variant", 0),
        "valid_changed": sum(r["status"] != "alternative representation" for r in valid),
        "valid_altrep": sum(r["status"] == "alternative representation" for r in valid),
        "timing": dict(tim),
        "concept": dict(con),
        "before": tim.get("act before submission", 0),
        "after": tim.get("act after submission", 0),
        "mandatory": tim.get("mandatory change, no act", 0),
        "not_cited": tim.get("act not cited", 0),
        "not_identified": tim.get("act not identified", 0),
        "with_act": sum(bool(r["act_keys"]) for r in rows),
        "aphia_missing": sum(r["aphia"] is None for r in rows),
    }


def _revision_facts(cfg: Config, f: dict, tables: dict, dq: dict, ov, cw, cache) -> None:
    """Facts added in response to peer review: census, causes, cells, tiers, provenance."""
    from anemone_kg.dq import crosstable

    rep = cfg.path("reports")
    f["census"] = dq["extraction_census"]
    xt = dq["cross_table"]
    disc = _csv(rep / "cross_table_review.csv")
    f["xt"] = {**xt, "rows_list": disc.to_dict("records")}
    f["tiers"] = xt["tiers"]
    f["tiers"]["specimen_confirmed"] = xt["tiers"].get("SurveyVouchered", 0) + xt["tiers"].get(
        "MuseumConfirmed", 0
    )
    q07 = pd.DataFrame(f["q"]["q07"])
    L = {k: v for k, v in crosstable.BEST_TIER.items()}  # class -> label printed by q07

    def share(g: pd.DataFrame) -> dict:
        d = g.groupby("best").cells.sum().to_dict()
        m = int(g.cells.sum())
        k = {c: int(d.get(lab, 0)) for c, lab in L.items()}
        lo = k["lit_agudo"] + k["lit_other"]
        return {
            "n": m,
            **k,
            "lit_only": lo,
            "pct_lit_only": round(100 * lo / m),
            "pct_specimen": round(100 * k["specimen"] / m),
            "pct_museum_code": round(100 * k["museum_code"] / m),
        }

    loc = tables["locality"]
    areas = loc[loc.locality_level == "area"]
    allc = share(q07)
    n = allc["n"]
    f["cells"] = {
        **allc,
        "agudo_alone": allc["lit_agudo"],
        "pct_agudo_alone": round(100 * allc["lit_agudo"] / n),
        "code_only": allc["survey_code"] + allc["museum_code"] + allc["survey_never"],
        "by_region": {r: share(g) for r, g in q07.groupby("region")},
        "visited": share(q07[q07.visited]),
        "not_visited": share(q07[~q07.visited]),
        "region_by_visited": xt["region_by_visited"],
        "areas_per_region": areas.groupby("region").size().to_dict(),
        "visited_areas": int(areas.sampled_in_study.sum()),
        "visited_per_region": areas[areas.sampled_in_study.astype(bool)]
        .groupby("region")
        .size()
        .to_dict(),
        "accepted_n": xt["accepted_cells"],
        "accepted_lit_only": xt["accepted_cell_support"].get(
            "literature only: Agudo (1987) alone", 0
        )
        + xt["accepted_cell_support"].get("literature only: other or several sources", 0),
        "scenario_share": {
            k: round(100 * v["specimen_share"], 1) for k, v in xt["scenarios"].items()
        },
    }
    f["cells"]["accepted_pct_lit_only"] = round(
        100 * f["cells"]["accepted_lit_only"] / f["cells"]["accepted_n"]
    )
    # museum-route tier per stratum: museum codes backed by a matching specimen
    tiers = crosstable.evidence_tiers(tables)
    dd = tables["distribution"].assign(tier=lambda x: x.distribution_id.map(tiers))
    vis = dict(zip(areas.locality_id, areas.sampled_in_study.astype(bool), strict=True))
    mus = dd[dd.evidence_kind == "mohbr_collection"].assign(v=lambda x: x.locality_id.map(vis))
    f["cells"]["museum_route"] = {
        lab: {
            "codes": int((mus.v == flag).sum()),
            "confirmed": int(((mus.v == flag) & (mus.tier == "MuseumConfirmed")).sum()),
        }
        for lab, flag in (("visited", True), ("not_visited", False))
    }
    acc = crosstable.accepted_ids(tables)
    t1 = tables["taxon"][tables["taxon"].name_roles.fillna("").str.contains("table1")]
    occ = tables["occurrence"]
    t3o = occ[occ.record_source == "table3"]
    sites = loc[loc.locality_level == "site"]
    with_coords = set(sites.loc[sites.decimal_latitude.notna(), "parent_locality_id"])
    ref = tables["reference"]
    lit_years = sorted(int(y) for y in ref.short_citation.str.extract(r"\((\d{4})\)")[0].dropna())
    wm2 = tables["taxon_mapping"]
    wm2 = wm2[(wm2.object_source == "worms") & wm2.object_id.notna()]
    shared = wm2[wm2.object_id.duplicated(keep=False)].sort_values("object_id")
    cov = _csv(rep / "ncbi_coverage.csv")
    q03_names = {r["name"] for r in f["q"]["q03"]["rows"]}
    linked = cov[cov.taxid.notna()].nucleotide_records
    f["extra"] = {
        "sites_t2": int(sites.source_ref.str.startswith("Table 2").sum()),
        "sites_t3": int(sites.source_ref.str.startswith("Table 3").sum()),
        "t3_dated": int(t3o.event_date.notna().sum()),
        # valid calendar dates (day precision, or year-month for a printed day 01)
        "t3_parseable": int(t3o.event_date.fillna("").str.len().isin([7, 10]).sum()),
        "t3_day_dated": int(t3o.event_date.fillna("").str.len().eq(10).sum()),
        "t3_date_min": str(t3o.event_date.dropna().min())[:4],
        "t3_date_max": str(t3o.event_date.dropna().max())[:4],
        "lit_year_min": lit_years[0],
        "lit_year_max": lit_years[-1],
        "sampled_without_coords": sorted(
            areas.loc[
                areas.sampled_in_study & ~areas.locality_id.isin(with_coords), "locality_name"
            ]
        ),
        "shared_worms": [" / ".join(g.subject_label) for _, g in shared.groupby("object_id")],
        "t4_unresolved_ncbi": sorted(q03_names & set(cov.loc[cov.taxid.isna(), "name"])),
        **_insdc(cov, tables["taxon_mapping"]),
        "ncbi_fallback_genus_change": _fallback_genus_changes(tables["taxon_mapping"]),
        **_vouchers(tables, disc),
        "id_changes": dict(Counter(crosstable.identification_changes(tables).values())),
        "associated_links": len(crosstable.supporting_specimens(tables)),
    }
    f["species"] = {
        "table1_names": len(t1),
        "accepted": len({acc.get(x) for x in t1.taxon_id}),
        "dagger": int(t1.flag_invalid_in_source.sum()),
        "species_rank": int((t1.taxon_rank == "species").sum()),
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
        # the source names the order Zoanthidea in Table 1 and Zoantharia in the accounts (and
        # WoRMS uses Zoantharia): one order, counted once under the Table 1 name
        "by_order": cov.assign(ok=cov.taxid.notna())
        .groupby(cov.order.replace({"Zoantharia": "Zoanthidea"}).fillna("name variant"))
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
        "crosswalk_t3_exact": int(((t3.status == "accepted") & (t3.rule == "exact")).sum()),
        "crosswalk_t3_rejected": int((t3.status == "rejected").sum()),
        "areas_with_coords": int(
            loc[(loc.locality_level == "site") & loc.decimal_latitude.notna()]
            .parent_locality_id.dropna()
            .nunique()
        ),
    }
    f["curated_by_file"] = f["canon"]["curated_by_file"]
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


def _ncbi_label(mapping: pd.DataFrame, taxid) -> str:
    m = mapping[mapping.object_id == f"NCBITaxon:{int(float(taxid))}"]
    return str(m.object_label.iloc[0]) if len(m) else str(taxid)


def _vouchers(tables: dict, disc: pd.DataFrame) -> dict:
    """Species of the survey with and without a Table 2 voucher (round 3, R1 M2)."""
    ident = tables["identification"]
    occ = tables["occurrence"]
    t2 = set(occ[occ.record_source == "table2"].occurrence_id)
    taxa = tables["taxon"].set_index("taxon_id")
    cur = ident[ident.is_current & ident.occurrence_id.isin(t2) & ident.taxon_id.notna()]
    sp = {t for t in cur.taxon_id if taxa.taxon_rank.get(t) == "species"}
    d = tables["distribution"]
    surveyed = set(d[d.evidence_kind == "this_survey"].taxon_id)
    never = sorted(taxa.scientific_name[t] for t in surveyed - set(cur.taxon_id))
    sv = disc[disc.survey_code_no_voucher & disc.comparable]
    return {
        "t2_species": len(sp),
        "t2_higher": sorted({taxa.scientific_name[t] for t in set(cur.taxon_id) - sp}),
        "survey_species": len(surveyed),
        "never_vouchered": never,
        "survey_cells_elsewhere": int(sv.vouchered_elsewhere.sum()),
        "survey_cells_never": int((~sv.vouchered_elsewhere).sum()),
        # cells behind a specimen without a code whose Table 1 cell holds other codes: the
        # rendered-image check cannot see a missing code there, so their crops were inspected
        "occupied_crops": int(
            (
                disc.comparable
                & (disc.survey_specimen_no_code | disc.museum_specimen_no_code)
                & (disc.table1_codes != "-")
            ).sum()
        ),
    }


def _insdc(cov: pd.DataFrame, mapping: pd.DataFrame) -> dict:
    """Nucleotide record counts per distinct species-rank NCBI node (round 3, R3 m1: per name
    the statistic counted five nodes twice and mixed in a family and a genus)."""
    lk = cov[cov.taxid.notna()]
    sp = lk[lk["rank"] == "species"].drop_duplicates("taxid")
    n = sp.nucleotide_records
    zero = sp[n == 0]
    return {
        "insdc_names": len(lk),
        "insdc_nodes": int(lk.taxid.nunique()),
        "insdc_species_nodes": len(sp),
        "insdc_higher": sorted(lk[lk["rank"] != "species"].name),
        "insdc_min": int(n.min()),
        "insdc_q1": float(n.quantile(0.25)),
        "insdc_median": float(n.median()),
        "insdc_q3": float(n.quantile(0.75)),
        "insdc_max": int(n.max()),
        "insdc_max_name": _ncbi_label(mapping, sp.loc[n.idxmax(), "taxid"]),
        "insdc_max_via": sp.loc[n.idxmax(), "ncbi_result"] == "via_accepted_name",
        "insdc_le10": int((n <= 10).sum()),
        "insdc_over_1000": int((n > 1000).sum()),
        "insdc_zero": sorted(zero.name),
    }


def _tier_rule_row(f: dict) -> dict:
    """Why the tier counts differ from W08/W10. Both rules compare only areas from which the
    matching specimen table has a *currently identified* specimen; the tiers cover every area.
    The two must reconcile exactly (bug once, round 3: the explanation was off by one)."""
    x = pd.DataFrame(f["xt"]["tier_rule_crosstab"])
    t = f["tiers"]
    w08, w10 = f["dq"]["by_id"]["W08"], f["dq"]["by_id"]["W10"]
    unv = x[x.tier == "SurveyUnvouchered"]
    mus = x[x.tier.isin(["MuseumUntraced", "MuseumUnconfirmed", "MuseumReidentified"])]
    unv_out = int(unv[~unv.area_has_specimens].assertions.sum())
    mus_out = int(mus[~mus.area_has_specimens].assertions.sum())
    n_mus = int(mus.assertions.sum())
    if t["SurveyUnvouchered"] - unv_out != w08 or n_mus - mus_out != w10:
        raise ValueError("tier counts do not reconcile with W08/W10")
    return {
        "count": f"{t['SurveyUnvouchered']} survey codes without a specimen from the area vs "
        f"W08 = {w08}; {n_mus} museum codes without a matching specimen vs W10 = {w10}",
        "derivation": "W08 and W10 compare only areas from which the matching table has a "
        f"currently identified specimen: {unv_out} survey codes and {mus_out} museum codes "
        f"lie in other areas ({t['SurveyUnvouchered']} - {unv_out} = {w08}; "
        f"{n_mus} - {mus_out} = {w10})",
    }


def _fallback_genus_changes(m: pd.DataFrame) -> int:
    fb = m[m.match_type == "via_accepted_name"]
    return int(
        sum(
            str(a).split()[0] != str(b).split()[0]
            for a, b in zip(fb.subject_label, fb.object_label, strict=True)
        )
    )


def _reconciliation(f: dict) -> list[dict]:
    """One row per published count that a reader cannot rebuild from the text alone."""
    s, c, r, d, g = f["src"], f["canon"], f["res"], f["dq"], f["graph"]
    dc = g["derived_by_class"]
    n_fields = f["census"]["table2"]["fields_checked"] + f["census"]["table3"]["fields_checked"]
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
            "count": f"{dc.get('dcterms:Location', 0)} dcterms:Location vs "
            f"{c['locality']} locality rows",
            "derivation": f"{c['locality']} localities ({loc['areas']} areas + {loc['sites']} "
            "sites) + 4 region nodes (the article's own grouping of its Table 1 columns); areas "
            "per region: "
            + ", ".join(f"{k} {v}" for k, v in f["cells"]["areas_per_region"].items()),
        },
        {
            "count": f"{loc['sites']} sites by table",
            "derivation": f"{f['extra']['sites_t2']} collecting sites of Table 2 + "
            f"{f['extra']['sites_t3']} localities of Table 3",
        },
        {
            "count": f"{f['xt']['uncertain_links']} uncertain links",
            "derivation": "Table 3 crosswalk rows that are neither an exact name nor a printed "
            f"park name: {loc['crosswalk_t3_linked'] - loc['crosswalk_t3_exact']} name-in-area "
            f"or spelling-variant links (of the {loc['crosswalk_t3_linked']} linked, "
            f"{loc['crosswalk_t3_exact']} are exact) + "
            f"{loc['crosswalk_t3_rejected']} links the curator rejected",
        },
        {
            "count": f"{n_fields:,} specimen fields",
            "derivation": "128 rows x 8 fields (Table 2) + 84 rows x 7 fields (Table 3); "
            f"{f['census']['table3']['fields_blank']} field is blank in the source and agrees "
            "when both readings find it blank",
        },
        {
            "count": f"{f['curated_by_file']['event_dates']} event-date rows",
            "derivation": "4 visited areas dated November 2012 in the Methods + 1 row for Isla "
            "de Cubagua, left undated because the source states no date; Chichiriviche de la "
            "Costa has neither a date row nor a Table 2 specimen",
        },
        {
            "count": f"{wn['matched']} WoRMS records matched by {r['n_taxa']} names",
            "derivation": "two pairs of names share a record: "
            + "; ".join(f["extra"]["shared_worms"])
            + " (a misspelling and its correct form)",
        },
        {
            "count": f"{f['envo']['matches']} habitat phrase matches",
            "derivation": f"{f['envo']['accepted']} annotated + {f['envo']['negated']} negated + "
            f"{f['envo']['matches'] - f['envo']['accepted'] - f['envo']['negated']} 'coral "
            "rubble' (one per account; no ENVO class). Biotic substrates are not in the phrase "
            "vocabulary, so they are not counted here",
        },
        _tier_rule_row(f),
        {
            "count": f"{f['xt']['cells']} discrepant cells vs "
            f"{sum(d['by_id'][w] for w in ('W08', 'W09', 'W10', 'W11'))} W08-W11 rows",
            "derivation": "cells merge both directions for one accepted name and area, and "
            "include areas the specimen tables do not cover; rows count each direction "
            f"separately and only in covered areas. A further {f['xt']['not_comparable']} "
            "cells (Actiniidae sp. of the specimen tables) have no Table 1 row and are not "
            "comparable",
        },
        {
            "count": f"{f['xt']['cells']} cells = {f['xt']['explained']} + "
            f"{f['xt']['possible']} + {f['xt']['code_level_only']} + {f['xt']['unexplained']}",
            "derivation": "explained by the article (re-identified or not identified) + "
            "possibly explained by a same-family specimen identified above species level in "
            "the table the missing specimen would be in + differing only in the code + "
            "unexplained",
        },
        {
            "count": f"{f['cells']['pct_specimen']}% of cells on a specimen from the area",
            "derivation": "by link scenario: "
            + ", ".join(
                f"{k.replace('_', ' ')} {v}%" for k, v in f["cells"]["scenario_share"].items()
            ),
        },
        {
            "count": f"{f['xt']['table3_without_area']} Table 3 specimens outside the comparison",
            "derivation": "no locality ('-'), a locality with no Table 1 column, or a rejected "
            "link: they are compared with no Table 1 area in either direction",
        },
        {
            "count": f"{f['graph']['cls']['dwc:Occurrence']} occurrences",
            "derivation": f"{c['occurrence']} specimens (PreservedSpecimen) + "
            f"{c['distribution']} Table 1 assertions ({f['codes']['mohbr']} MaterialCitation for "
            f"museum codes, {c['distribution'] - f['codes']['mohbr']} Occurrence for the others),"
            f" of which {f['extra']['associated_links']} cite the specimen they rest on "
            "(akv:citesSpecimen); the two classes are not to be counted together",
        },
        {
            "count": f"{d['by_id'].get('W12', 0)} dates published as year-month",
            "derivation": f"Table 3 dates printed with day 01: {d['by_id'].get('W12', 0)} of "
            f"{f['extra']['t3_parseable']} parseable dates, against about "
            f"{round(f['extra']['t3_parseable'] / 30.4)} expected if days were uniform",
        },
        {
            "count": "three different sets of four",
            "derivation": f"{c['typos']} misspelt names in Table 2 (name variants); "
            f"{r['worms']['curated']} WoRMS links accepted after curation; "
            f"{f['q']['q03']['spelling']} spelling-only rows of Table 4",
        },
    ]
