"""Stage 3 - resolve: canonical taxa -> WoRMS/GBIF/NCBI; habitat text -> ENVO."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import yaml

from anemone_kg.cli import stage
from anemone_kg.config import Config
from anemone_kg.logs import log_counts
from anemone_kg.resolve.habitats import EnvoLookup, annotate
from anemone_kg.resolve.http import CachedHttp
from anemone_kg.resolve.taxa import Override, TaxonResolver
from anemone_kg.stages.canonicalize import canonical_dir

log = logging.getLogger(__name__)

SERVICES = ("worms", "gbif", "ncbi")


def make_http(cfg: Config) -> CachedHttp:
    r = cfg.resolution
    return CachedHttp(
        cfg.path("cache"),
        r["user_agent"],
        r["request_timeout_s"],
        r["min_interval_s"],
        r["offline"],
    )


def load_overrides(path: Path) -> dict[tuple[str, str], Override]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    bad = set(df.decision) - {"accept", "reject"}
    if bad:
        raise ValueError(f"{path.name}: unknown decisions {bad}")
    return {
        (r.subject_label, r.object_id): Override(
            r.service, r.object_id, r.decision, r.evidence, r.predicate_id or None
        )
        for r in df.itertuples()
    }


def resolve_all(cfg: Config, http: CachedHttp) -> dict[str, pd.DataFrame]:
    canon = canonical_dir(cfg)
    taxa = pd.read_csv(canon / "taxon.csv")
    resolver = TaxonResolver(
        http, load_overrides(cfg.path("mappings") / "resolution_overrides.csv")
    )
    rows = []
    for t in taxa.itertuples():
        auth = (
            t.scientific_name_authorship if isinstance(t.scientific_name_authorship, str) else None
        )
        w = resolver.worms(t.taxon_id, t.scientific_name, t.taxon_rank, auth)
        accepted_name = None
        if w.status == "accepted" and w.object_id:
            rec = resolver.worms_records[int(w.object_id.split(":")[1])]
            accepted_name = rec.valid_name if rec.valid_name != rec.scientific_name else None
        rows += [
            w,
            resolver.gbif(t.taxon_id, t.scientific_name, t.taxon_rank),
            resolver.ncbi(t.taxon_id, t.scientific_name, t.taxon_rank, accepted_name),
        ]
    unused = set(resolver.overrides) - resolver.used_overrides
    if unused:
        raise ValueError(f"override rows never applied (stale or mistyped): {sorted(unused)}")
    mappings = pd.DataFrame([r.as_row() for r in rows])
    mappings.insert(0, "mapping_id", [f"{r.subject_id}:{r.object_source}" for r in rows])
    worms = pd.DataFrame([asdict(r) for r in resolver.worms_records.values()])

    stmts = pd.read_csv(canon / "habitat_statement.csv")
    vocab = pd.read_csv(cfg.path("mappings") / "habitat_vocabulary.csv")
    ann = annotate(stmts, vocab, EnvoLookup(http))
    habitat = pd.DataFrame([a.as_row() for a in ann])
    habitat.insert(0, "annotation_id", [f"{a.habitat_statement_id}:{a.char_start}" for a in ann])
    return {"taxon_mapping": mappings, "worms_record": worms, "habitat_annotation": habitat}


def write_sssom(df: pd.DataFrame, path: Path, cfg: Config) -> None:
    """SSSOM TSV: YAML metadata block as '#' comments, then the mapping table."""
    meta = {
        "mapping_set_id": f"{cfg.namespace['base']}mappings/taxa",
        "mapping_set_description": "Taxon names in González-Muñoz et al. (2016) mapped to "
        "WoRMS, GBIF and NCBI Taxonomy. Only status=accepted rows are asserted mappings.",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "curie_map": {"ak": cfg.namespace["base"], **cfg.resolution["curie_map"]},
    }
    cols = [
        "subject_id",
        "subject_label",
        "predicate_id",
        "object_id",
        "object_label",
        "mapping_justification",
        "confidence",
        "mapping_tool",
        "mapping_date",
        "comment",
    ]
    acc = df[df.status == "accepted"].copy()
    acc["subject_id"] = "ak:taxon/" + acc["subject_id"]
    header = "".join(f"#{line}\n" for line in yaml.safe_dump(meta, sort_keys=False).splitlines())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + acc[cols].to_csv(sep="\t", index=False), encoding="utf-8")


def report_markdown(t: dict[str, pd.DataFrame], n_statements: int, http: CachedHttp) -> str:
    m, ann = t["taxon_mapping"], t["habitat_annotation"]
    out = ["# Identifier resolution report", ""]
    out += [
        "## Taxa: status per service",
        "",
        "| service | accepted | candidate | ambiguous | unresolved |",
        "|---|---:|---:|---:|---:|",
    ]
    for s in SERVICES:
        c = m[m.object_source == s].status.value_counts()
        out.append(
            f"| {s} | {c.get('accepted', 0)} | {c.get('candidate', 0)} | "
            f"{c.get('ambiguous', 0)} | {c.get('unresolved', 0)} |"
        )
    out += ["", "## Match types (accepted rows)", ""]
    acc = m[m.status == "accepted"]
    for s in SERVICES:
        out.append(
            f"- {s}: "
            + ", ".join(
                f"{k} {v}" for k, v in acc[acc.object_source == s].match_type.value_counts().items()
            )
        )

    w = m[(m.object_source == "worms") & (m.match_type == "exact_synonym")]
    out += [
        "",
        f"## Names whose WoRMS accepted name differs from the paper ({len(w)})",
        "",
        "| name in paper | WoRMS record (status) | accepted name |",
        "|---|---|---|",
    ]
    wr = t["worms_record"].set_index("aphia_id")
    for r in w.itertuples():
        rec = wr.loc[int(r.object_id.split(":")[1])]
        out.append(
            f"| {r.subject_label} | {r.object_id} ({rec.taxonomic_status}) | "
            f"{rec.valid_name} (worms:{int(rec.valid_aphia_id)}) |"
        )

    pending = m[m.status.isin(["candidate", "ambiguous", "unresolved"])]
    out += [
        "",
        f"## Needs attention ({len(pending)} rows) - nothing here was guessed",
        "",
        "| name | service | status | candidate | confidence | comment |",
        "|---|---|---|---|---:|---|",
    ]
    for r in pending.sort_values(["status", "subject_label"]).itertuples():
        conf = "" if pd.isna(r.confidence) else f"{r.confidence:.2f}"
        cand = f"{r.object_label} ({r.object_id})" if isinstance(r.object_id, str) else ""
        out.append(
            f"| {r.subject_label} | {r.object_source} | {r.status} | {cand} | "
            f"{conf} | {r.comment if isinstance(r.comment, str) else ''} |"
        )

    out += ["", "## Habitats -> ENVO", ""]
    c = ann.status.value_counts()
    out.append(f"- {len(ann)} phrase matches: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    good = ann[ann.status == "accepted"]
    out.append(
        f"- {good.habitat_statement_id.nunique()} of {n_statements} habitat "
        "statements have at least one ENVO term"
    )
    none = sorted(set(ann.habitat_statement_id) ^ set(good.habitat_statement_id))
    if none:
        out.append(f"- statements with no ENVO term: {len(none)} (see habitat_annotation.csv)")
    out += ["", "| ENVO term | id | kind | statements |", "|---|---|---|---:|"]
    for (lab, eid, kind), g in good.groupby(["envo_label", "envo_id", "habitat_kind"]):
        out.append(f"| {lab} | {eid} | {kind} | {g.habitat_statement_id.nunique()} |")
    neg = ann[ann.status == "negated"]
    out += [
        "",
        "Negated (not annotated): "
        + "; ".join(f"'{r.matched_text}' ({r.comment})" for r in neg.itertuples())
        or "none",
    ]
    unres = ann[ann.status == "unresolved"].envo_label.unique().tolist()
    out.append(f"Unresolved labels (no ENVO class): {', '.join(unres) or 'none'}")
    out += [
        "",
        "## Cache",
        "",
        f"- responses served from cache: {http.stats['hit']}, fetched: {http.stats['network']}",
    ]
    out.append("")
    return "\n".join(out)


@stage("resolve")
def resolve(cfg: Config) -> None:
    http = make_http(cfg)
    tables = resolve_all(cfg, http)
    canon = canonical_dir(cfg)
    for name, df in tables.items():
        df.to_csv(canon / f"{name}.csv", index=False)
        log.info("[resolve] %s: %d rows", name, len(df))
    taxa = pd.read_csv(canon / "taxon.csv")
    log_counts(
        log,
        "resolve:taxa x services -> taxon_mapping",
        len(taxa) * len(SERVICES),
        len(tables["taxon_mapping"]),
        "one row per taxon and service, resolved or not",
    )
    write_sssom(
        tables["taxon_mapping"],
        cfg.path("processed") / "mappings" / "taxon_mappings.sssom.tsv",
        cfg,
    )
    (cfg.path("reports") / "resolution_report.md").write_text(
        report_markdown(tables, len(pd.read_csv(canon / "habitat_statement.csv")), http),
        encoding="utf-8",
    )
    log.info("[resolve] cache hits=%d network=%d", http.stats["hit"], http.stats["network"])
