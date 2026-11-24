"""Stage 6 - shacl: validate the built graph against shapes/anemone_kg.shapes.ttl.

Violations stop the pipeline; warnings and info are reported (they mirror the
data-quality warnings: gaps in the source, not errors in the graph).

The report graph is canonicalised (blank-node labels from rdflib.compare) so
the committed reports/shacl_report.ttl is byte-identical across runs.
"""

from __future__ import annotations

import json
import logging
from collections import Counter

import pyshacl
import rdflib
from rdflib import RDF, RDFS, Namespace
from rdflib.compare import to_canonical_graph

from anemone_kg.cli import stage
from anemone_kg.config import Config

log = logging.getLogger(__name__)
SH = Namespace("http://www.w3.org/ns/shacl#")


class ShaclViolationError(RuntimeError):
    """The graph does not conform to its shapes."""


def validate_graph(data: rdflib.Graph, shapes: rdflib.Graph) -> tuple[bool, rdflib.Graph]:
    conforms, report, _ = pyshacl.validate(
        data,
        shacl_graph=shapes,
        inference="none",
        advanced=True,
        allow_warnings=True,
        abort_on_first=False,
    )
    return conforms, report


def results(report: rdflib.Graph, data: rdflib.Graph) -> list[dict]:
    out = []
    for r in report.subjects(RDF.type, SH.ValidationResult):
        focus = report.value(r, SH.focusNode)
        out.append(
            {
                "severity": str(report.value(r, SH.resultSeverity)).rsplit("#", 1)[1],
                "shape": report.namespace_manager.normalizeUri(report.value(r, SH.sourceShape))
                if isinstance(report.value(r, SH.sourceShape), rdflib.URIRef)
                else "(property shape)",
                "message": str(report.value(r, SH.resultMessage)),
                "focus": str(focus),
                "label": str(data.value(focus, RDFS.label) or ""),
                "path": data.namespace_manager.normalizeUri(report.value(r, SH.resultPath))
                if report.value(r, SH.resultPath) is not None
                else "",
            }
        )
    return sorted(out, key=lambda d: (d["severity"], d["message"], d["focus"]))


def to_markdown(conforms: bool, res: list[dict], n_shapes: int, data_triples: int) -> str:
    by_sev = Counter(r["severity"] for r in res)
    lines = [
        "# SHACL validation report",
        "",
        f"**Conforms: {'yes' if conforms else 'NO'}** - {data_triples} data triples validated "
        f"against {n_shapes} node shapes (pySHACL, advanced mode for SPARQL targets and "
        "constraints, no inference).",
        "",
        "| severity | results |",
        "|---|---:|",
        *[f"| {s} | {by_sev.get(s, 0)} |" for s in ("Violation", "Warning", "Info")],
        "",
        "Violations stop the pipeline. Warnings and Info record gaps in the source that "
        "the data-quality stage also reports; they are not errors in the graph.",
        "",
        "## Results by message",
        "",
        "| severity | message | count |",
        "|---|---|---:|",
    ]
    for (sev, msg), n in sorted(Counter((r["severity"], r["message"]) for r in res).items()):
        lines.append(f"| {sev} | {msg} | {n} |")
    lines += [
        "",
        "## Focus nodes",
        "",
        "| severity | focus node | label | path |",
        "|---|---|---|---|",
    ]
    for r in res:
        lines.append(f"| {r['severity']} | `{r['focus']}` | {r['label']} | {r['path']} |")
    lines.append("")
    return "\n".join(lines)


@stage("shacl")
def shacl(cfg: Config) -> None:
    data = rdflib.Graph().parse(cfg.path("processed") / "anemone_kg.ttl")
    shapes = rdflib.Graph().parse(cfg.root / "shapes" / "anemone_kg.shapes.ttl")
    conforms, report = validate_graph(data, shapes)
    res = results(report, data)
    reports = cfg.path("reports")
    canon = to_canonical_graph(report)
    canon.namespace_manager = report.namespace_manager
    canon.serialize(reports / "shacl_report.ttl", format="turtle")
    n_shapes = len(set(shapes.subjects(RDF.type, SH.NodeShape)))
    (reports / "shacl_report.md").write_text(
        to_markdown(conforms, res, n_shapes, len(data)), encoding="utf-8"
    )
    summary = {
        "conforms": conforms,
        "node_shapes": n_shapes,
        "results": dict(Counter(r["severity"] for r in res)),
    }
    (reports / "shacl_report.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    log.info("[shacl] conforms=%s results=%s", conforms, summary["results"])
    if not conforms:
        raise ShaclViolationError("graph violates its SHACL shapes - see reports/shacl_report.md")
