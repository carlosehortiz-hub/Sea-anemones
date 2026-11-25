"""Manuscript figures, generated from the pipeline outputs.

Figures 1-2 are diagrams written as SVG (vector, print-sharp, no layout engine).
Figures 3-4 are data charts (matplotlib, SVG output). Colour follows the
data-viz method used for this project: categorical slots in fixed order from a
validated palette (blue, orange, aqua; CVD-safe adjacent pairs), unresolved in
neutral grey, thin marks, recessive axes, a legend plus direct value labels
(the aqua slot is below 3:1 contrast, so every value is printed), and every
number also appears in a table of the manuscript.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#b9b8b3"
VIOLET, YELLOW = "#7a4fc4", "#f0c53c"
INK, INK2, RULE = "#0b0b0b", "#52514e", "#d9d8d3"
FONT = "Liberation Sans"

plt.rcParams.update(
    {
        "font.family": FONT,
        "font.size": 8,
        "axes.edgecolor": RULE,
        "axes.labelcolor": INK2,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "axes.linewidth": 0.6,
        "svg.fonttype": "none",
        "svg.hashsalt": "anemone-kg",
    }
)


# ------------------------------------------------------------------ diagrams
def _box(x, y, w, h, title, sub="", fill="#f3f7fd", stroke=BLUE, title_size=10):
    t = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.2"/>',
        f'<text x="{x + w / 2}" y="{y + (h / 2 - 3 if sub else h / 2 + 4)}" text-anchor="middle" '
        f'font-size="{title_size}" font-weight="700" fill="{INK}">{escape(title)}</text>',
    ]
    for i, line in enumerate(sub.split("\n") if sub else []):
        t.append(
            f'<text x="{x + w / 2}" y="{y + h / 2 + 10 + i * 11}" text-anchor="middle" '
            f'font-size="8.2" fill="{INK2}">{escape(line)}</text>'
        )
    return "\n".join(t)


def _arrow(x1, y1, x2, y2, label="", dashed=False, color=INK2):
    d = ' stroke-dasharray="4 3"' if dashed else ""
    s = (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.1"'
        f'{d} marker-end="url(#ah)"/>'
    )
    if label:
        s += (
            f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 4}" text-anchor="middle" '
            f'font-size="7.6" fill="{INK2}" font-style="italic">{escape(label)}</text>'
        )
    return s


def _svg(w, h, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
        f'height="{h}" font-family="{FONT}, Arial, sans-serif">'
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        f'fill="{INK2}"/></marker></defs>{body}</svg>\n'
    )


def pipeline_svg(f: dict) -> str:
    s, c, r, d, g, sh = f["src"], f["canon"], f["res"], f["dq"], f["graph"], f["shacl"]
    nq = f["q"]["n_sparql"]
    W, H, bw, bh, gap, y0 = 760, 248, 82, 66, 12, 34
    stages = [
        ("PDF", f"{s['pages']} pages\nsha256-pinned"),
        ("1 extract", "Tables 1-3,\naccounts"),
        ("2 canonical", f"LinkML · DwC\n{c['rules']} rules"),
        ("3 resolve", "WoRMS · GBIF\nNCBI · ENVO"),
        (
            "4 validate",
            f"{d['schema_checks']} checks\n{d['n_critical']} critical rules\ncensus 0 diffs",
        ),
        ("5 build", f"RDF, {g['triples']:,}\ntriples"),
        ("6 SHACL", f"{sh['shapes']} shapes,\n{sh['violation']} violations"),
        ("7 query", f"{f['q']['n_sparql']} SPARQL\n+ {f['q']['n_sql']} SQL"),
    ]
    out, xs = [], []
    for i, (title, sub) in enumerate(stages):
        x = 10 + i * (bw + gap)
        xs.append(x)
        gate = title.startswith(("4", "6"))
        out.append(
            _box(
                x,
                y0,
                bw,
                bh,
                title,
                sub,
                fill="#fff4ef" if gate else "#f3f7fd",
                stroke=ORANGE if gate else BLUE,
                title_size=9.5,
            )
        )
        if i:
            out.append(_arrow(x - gap + 1, y0 + bh / 2, x - 2, y0 + bh / 2))
    for i in (4, 6):
        x = xs[i] + bw / 2
        out.append(_arrow(x, y0 + bh + 2, x, y0 + bh + 30, dashed=True, color=ORANGE))
        out.append(
            f'<text x="{x}" y="{y0 + bh + 44}" text-anchor="middle" font-size="8" '
            f'fill="{ORANGE}" font-weight="700">stop the pipeline</text>'
        )
    y2 = y0 + bh + 70
    for idx, (title, sub) in (
        (2, ("curated mappings", f"{c['curated_rows']} rows in\n{c['curated_files']} files")),
        (3, ("API cache", f"{r['cached']} responses,\ncommitted")),
        (
            5,
            ("endpoint", f"Oxigraph = rdflib\n({nq}/{nq} queries)"),
        ),
    ):
        x = xs[idx] - 3
        out.append(_box(x, y2, bw + 6, 50, title, sub, fill="#f4fbf8", stroke=AQUA, title_size=8.6))
        if idx == 5:
            out.append(_arrow(xs[5] + bw / 2, y0 + bh + 2, xs[5] + bw / 2, y2 - 2))
        else:
            out.append(_arrow(xs[idx] + bw / 2, y2 - 2, xs[idx] + bw / 2, y0 + bh + 2))
    out.append(
        f'<text x="10" y="18" font-size="9" fill="{INK2}">Every stage logs records in and '
        "out (0 dropped). A clean run reproduces every output byte for byte "
        "(end-to-end test, CI).</text>"
    )
    out.append(
        f'<text x="10" y="{H - 8}" font-size="8" fill="{INK2}">Blue: transformation '
        "stages. Orange: quality gates. Green: curated inputs, cache and the SPARQL "
        "endpoint.</text>"
    )
    return _svg(W, H, "\n".join(out))


def model_svg() -> str:
    W, H = 760, 330
    o = []
    B = lambda x, y, w, t, sub="", fill="#f3f7fd", stroke=BLUE: o.append(  # noqa: E731
        _box(x, y, w, 40, t, sub, fill=fill, stroke=stroke, title_size=9)
    )
    # specimen side
    B(20, 30, 130, "dwc:Occurrence", "PreservedSpecimen")
    B(20, 130, 130, "dwc:Event", "eventDate")
    B(20, 230, 130, "dcterms:Location", "site → area → region")
    B(230, 30, 120, "dwc:Organism")
    B(230, 130, 120, "dwc:Identification", "current / superseded")
    # names
    B(380, 130, 150, "dwc:Taxon", "name as used in the paper")
    B(590, 60, 150, "WoRMS record", "LSID · taxonomicStatus", fill="#f4fbf8", stroke=AQUA)
    B(590, 130, 150, "accepted name", "WoRMS record", fill="#f4fbf8", stroke=AQUA)
    B(590, 200, 150, "GBIF · NCBITaxon", "", fill="#f4fbf8", stroke=AQUA)
    # table 1 + habitat
    B(380, 30, 150, "dwc:Occurrence", "MaterialCitation (Table 1)")
    B(380, 240, 150, "akv:HabitatStatement", "dwc:habitat text")
    B(590, 270, 150, "ENVO class", "habitat · zone · substrate", fill="#f4fbf8", stroke=AQUA)
    # provenance
    o.append(
        _box(
            200,
            250,
            140,
            54,
            "source paper",
            "doi:10.1186/s41200-016-0016-7\nevery record → paper",
            fill="#fff4ef",
            stroke=ORANGE,
            title_size=9,
        )
    )
    a = o.append
    a(_arrow(85, 70, 85, 128, "dsw:atEvent"))
    a(_arrow(85, 170, 85, 228, "dsw:locatedAt"))
    a(_arrow(150, 50, 228, 50, "dsw:occurrenceOf"))
    a(_arrow(290, 130, 290, 72, "dsw:identifies"))
    a(_arrow(350, 150, 378, 150, ""))
    a(
        f'<text x="364" y="182" text-anchor="middle" font-size="7.6" fill="{INK2}" '
        'font-style="italic">dwciri:toTaxon</text>'
    )
    a(_arrow(455, 70, 455, 128, "dwciri:toTaxon"))
    a(_arrow(530, 140, 588, 85, "skos:exactMatch"))
    a(_arrow(665, 100, 665, 128, ""))
    a(
        f'<text x="672" y="118" font-size="7.6" fill="{INK2}" font-style="italic">'
        "akv:hasAcceptedName</text>"
    )
    a(_arrow(530, 160, 588, 215, "exact / closeMatch"))
    a(_arrow(455, 240, 455, 172, "dcterms:subject"))
    a(_arrow(530, 270, 588, 288, ""))
    a(
        f'<text x="546" y="302" text-anchor="middle" font-size="7.6" fill="{INK2}" '
        'font-style="italic">dwciri:habitat | substrate</text>'
    )
    a(_arrow(150, 270, 198, 275, ""))
    a(_arrow(380, 265, 342, 275, ""))
    a(
        f'<text x="200" y="322" font-size="7.6" fill="{INK2}" font-style="italic">'
        "prov:wasDerivedFrom + qualified derivation (table, row, page) from every record</text>"
    )
    return _svg(W, H, "\n".join(o))


# -------------------------------------------------------------------- charts
def _finish(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#ecebe7", linewidth=0.6)
    ax.set_axisbelow(True)


def resolution_svg(f: dict, path: Path) -> None:
    r = f["res"]
    services = [("worms", "WoRMS"), ("gbif", "GBIF"), ("ncbi", "NCBI Taxonomy")]
    lex = [r[s]["accepted"] - r[s]["curated"] - r[s]["via_accepted"] for s, _ in services]
    cur = [r[s]["curated"] for s, _ in services]
    via = [r[s]["via_accepted"] for s, _ in services]
    unr = [r[s]["unresolved"] for s, _ in services]
    fig, ax = plt.subplots(figsize=(6.6, 1.9), dpi=150)
    y = range(len(services))[::-1]
    left = [0] * 3
    small: dict = {}
    segs = [
        ("exact name (lexical)", lex, BLUE, "white"),
        ("curated variant", cur, ORANGE, INK),
        ("via WoRMS accepted name", via, AQUA, INK),
        ("not resolved", unr, GREY, INK),
    ]
    for label, vals, col, tcol in segs:
        ax.barh(
            list(y),
            vals,
            left=left,
            color=col,
            height=0.56,
            label=label,
            edgecolor="white",
            linewidth=1.5,
        )
        for yi, v, lft in zip(y, vals, left, strict=True):
            if v >= 3:
                ax.text(
                    lft + v / 2,
                    yi,
                    str(v),
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color=tcol,
                    fontweight="bold",
                )
            elif v:
                small.setdefault(yi, []).append(f"{v} {label}")
        left = [a + b for a, b in zip(left, vals, strict=True)]
    for yi, labels in small.items():
        ax.text(
            r["n_taxa"] + 0.8, yi, "  ".join(labels), ha="left", va="center", fontsize=7, color=INK2
        )
    rec = f["ncbi_cov"]["n_recovered"]
    ax.text(
        r["n_taxa"] + 0.8,
        y[-1],
        f"{rec} of {r['ncbi']['unresolved']} under\nanother name class",
        ha="left",
        va="center",
        fontsize=7,
        color=INK2,
    )
    ax.set_yticks(list(y), [lab for _, lab in services])
    ax.set_xlim(0, r["n_taxa"] + 14)
    ax.set_xticks(range(0, r["n_taxa"] + 1, 10))
    ax.set_xlabel(f"names used in the paper (n = {r['n_taxa']})")
    _finish(ax)
    ax.legend(
        ncol=4,
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.45, 1.0),
        fontsize=7.2,
        handlelength=1.2,
        columnspacing=1.2,
    )
    fig.tight_layout()
    fig.savefig(path, format="svg", metadata={"Date": None})
    plt.close(fig)


def evidence_svg(f: dict, path: Path) -> None:
    """Fig. 4: Table 1 cells by best evidence tier, per region and visited or not (query q07)."""
    rows = pd.DataFrame(f["q"]["q07"])
    from anemone_kg.dq.crosstable import BEST_TIER as L

    kinds = [
        (L["specimen"], "specimen from the area", BLUE, "white"),
        (L["survey_code"], "survey code, species vouchered elsewhere", AQUA, INK),
        (L["museum_code"], "museum code, no matching specimen", VIOLET, "white"),
        (L["survey_never"], "survey code, species never vouchered", YELLOW, INK),
        (L["lit_other"], "literature only: other", GREY, INK),
        (L["lit_agudo"], "literature only: Agudo (1987)", ORANGE, INK),
    ]
    regions = ["West Coast", "Central Coast", "East Coast", "Oceanic Islands"]
    n_areas = sum(f["cells"]["areas_per_region"].values())
    groups = [(r, rows[rows.region == r]) for r in regions] + [
        ("visited", rows[rows.visited]),
        ("not visited", rows[~rows.visited]),
    ]
    labels = [f"{r} ({f['cells']['areas_per_region'][r]} areas)" for r in regions] + [
        f"visited ({f['cells']['visited_areas']} areas)",
        f"not visited ({n_areas - f['cells']['visited_areas']} areas)",
    ]
    ypos = [7, 6, 5, 4, 2, 1]
    fig, ax = plt.subplots(figsize=(6.6, 3.2), dpi=150)
    left = [0] * len(groups)
    last_small: dict[float, float] = {}
    for key, label, col, tcol in kinds:
        vals = [int(g.loc[g.best == key, "cells"].sum()) for _, g in groups]
        ax.barh(
            ypos,
            vals,
            left=left,
            color=col,
            height=0.62,
            label=label,
            edgecolor="white",
            linewidth=1.5,
        )
        for yi, v, lft in zip(ypos, vals, left, strict=True):
            if v >= 5:
                ax.text(
                    lft + v / 2,
                    yi,
                    str(v),
                    ha="center",
                    va="center",
                    fontsize=7.3,
                    color=tcol,
                    fontweight="bold",
                )
            elif v:
                # small segments: label above the bar, pushed right so neighbours never overlap
                x = max(lft + v / 2, last_small.get(yi, -99) + 4.5)
                last_small[yi] = x
                ax.text(x, yi + 0.42, str(v), ha="center", va="bottom", fontsize=6.4, color=INK2)
        left = [a + b for a, b in zip(left, vals, strict=True)]
    for yi, (_, g), total in zip(ypos, groups, left, strict=True):
        lo = int(g.loc[g.best.str.startswith("literature"), "cells"].sum())
        sp = int(g.loc[g.best.str.startswith("specimen"), "cells"].sum())
        ax.text(
            total + 2,
            yi,
            f"n = {total}; {round(100 * sp / total)}% specimen, "
            f"{round(100 * lo / total)}% literature only",
            ha="left",
            va="center",
            fontsize=6.8,
            color=INK2,
        )
    ax.axhline(3, color=RULE, linewidth=0.8)
    ax.set_yticks(ypos, labels)
    ax.set_xlim(0, max(left) * 1.6)
    ax.set_xlabel("taxon \u00d7 area cells of Table 1 (printed name \u00d7 area), by best evidence")
    _finish(ax)
    ax.legend(
        ncol=3,
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.42, 1.0),
        fontsize=6.6,
        handlelength=1.2,
    )
    fig.tight_layout()
    fig.savefig(path, format="svg", metadata={"Date": None})
    plt.close(fig)


def write_all(f: dict, out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        k: out / f"{k}.svg"
        for k in ("fig1_pipeline", "fig2_model", "fig3_resolution", "fig4_evidence")
    }
    paths["fig1_pipeline"].write_text(pipeline_svg(f), encoding="utf-8")
    paths["fig2_model"].write_text(model_svg(), encoding="utf-8")
    resolution_svg(f, paths["fig3_resolution"])
    evidence_svg(f, paths["fig4_evidence"])
    return paths
