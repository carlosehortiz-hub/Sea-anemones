"""Build the manuscript: facts -> figures -> Jinja -> Markdown -> HTML -> PDF.

    python -m anemone_kg paper            # HTML + PDF (PDF needs Node + Playwright)
    python -m anemone_kg paper --no-pdf   # HTML only (what the tests use)

Guarantees, each enforced here or in tests/test_paper.py:
* no result is typed by hand - every number comes from `facts.collect`;
* every citation resolves to paper/references.yaml (an unknown key raises);
* every DOI reference matches its Crossref record (cached, checked offline);
* the reference list contains exactly the works cited, in alphabetical order;
* no template placeholder survives into the output.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import jinja2
import markdown
import yaml

from anemone_kg.config import Config, load_config
from anemone_kg.paper.facts import collect
from anemone_kg.paper.figures import write_all
from anemone_kg.paper.references import fetch_crossref, load_references, verify

log = logging.getLogger(__name__)


class CitationTracker:
    def __init__(self, refs):
        self.refs = refs
        self.used: list[str] = []

    def _use(self, key: str) -> str:
        if key not in self.refs:
            raise KeyError(f"unknown reference key {key!r}")
        if key not in self.used:
            self.used.append(key)
        return self.refs[key].cite_as

    def cite(self, *keys: str) -> str:
        """Parenthetical: (Author 2016; Other et al. 2012)."""
        return "(" + "; ".join(self._use(k) for k in keys) + ")"

    def citet(self, key: str) -> str:
        """Narrative: Author (2016)."""
        text = self._use(key)
        name, year = text.rsplit(" ", 1)
        return f"{name} ({year})"


def _env(root: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(root)),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    env.filters["thousands"] = lambda n: f"{int(n):,}"
    env.filters["longdate"] = lambda s: date.fromisoformat(s).strftime("%-d %B %Y")
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    env.filters["words"] = lambda n: words[int(n)] if 0 <= int(n) <= 10 else f"{int(n):,}"
    env.filters["Words"] = lambda n: env.filters["words"](n).capitalize()
    return env


def render(cfg: Config) -> tuple[str, dict, CitationTracker]:
    """The two-column review layout (paper/manuscript.pdf)."""
    front, body, f, tracker = render_parts(cfg)
    env = _env(cfg.root / "paper")
    html = env.get_template("template.html.j2").render(body=body, **front)
    return html, f, tracker


def render_parts(cfg: Config) -> tuple[dict, str, dict, CitationTracker]:
    """Front matter and body HTML, shared by every layout so the text never diverges."""
    root = cfg.root / "paper"
    f = collect(cfg)
    refs = load_references(root / "references.yaml")
    records = fetch_crossref(refs, root / "references" / "crossref", offline=True)
    problems = verify(refs, records)
    if problems:
        raise ValueError("references do not match Crossref: " + "; ".join(problems))
    tracker = CitationTracker(refs)
    env = _env(root)
    ctx = {
        "f": f,
        "cite": tracker.cite,
        "citet": tracker.citet,
        "ref": tracker._use,  # plain "Author year", for table cells
        "references": "@@REFS@@",
        "appendix": appendix_md(f),
    }

    front = yaml.safe_load((root / "front.yaml").read_text(encoding="utf-8"))

    def fill(text: str) -> str:
        return env.from_string(text).render(**ctx)

    front["abstract"] = {k: fill(v) for k, v in front["abstract"].items()}
    tracker._use("gonzalezmunoz2016")  # cited by name in the abstract
    body_md = env.get_template("manuscript.md.j2").render(**ctx)
    body = markdown.markdown(
        body_md, extensions=["tables", "md_in_html", "sane_lists"], output_format="html"
    )
    versions = {k: v for k, v in f["versions"].items()}
    ref_list = sorted((refs[k] for k in tracker.used), key=lambda r: r.sort_key())
    refs_html = (
        '<div class="refs">'
        + "".join(f"<p>{_md_inline(r.render(versions))}</p>" for r in ref_list)
        + "</div>"
    )
    body = body.replace("<p>@@REFS@@</p>", refs_html)
    # keep "Fig. 1", "Table 2", "p. 29" on one line
    body = re.sub(r"\b(Fig\.|Figs\.|Table|Tables|p\.|pp\.) (\d)", "\\1&nbsp;\\2", body)
    return front, body, f, tracker


def _cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ") if v == v and v is not None else ""


def _codes(text: str) -> str:
    return _cell(text).replace("this_survey", "*").replace("mohbr_collection", "a")


def appendix_md(f: dict) -> str:
    """Tables S1 and S2 for the layouts; the submission sends them as additional files."""
    from anemone_kg.dq.crosstable import CAUSES, KINDS

    short_kind = {
        "survey_code_no_voucher": "* without specimen",
        "museum_code_no_specimen": "a without specimen",
        "survey_specimen_no_code": "Table 2 specimen without *",
        "museum_specimen_no_code": "Table 3 specimen without a",
    }
    short_cause = {
        "reidentified": "re-identified",
        "unconfirmed": "not identified",
        "above_species": "above species (possible)",
        "other_code": "other code",
    }
    s1 = [
        '<div class="table-block wide" markdown="1">',
        '<p class="caption"><b>Table S1</b> Reconciliation of counts that cannot be rebuilt '
        "from the text alone (Additional file 1), generated from the pipeline outputs.</p>",
        "",
        "| Count | Derivation |",
        "|---|---|",
        *[f"| {_cell(r['count'])} | {_cell(r['derivation'])} |" for r in f["recon"]],
        "",
        "</div>",
    ]

    def status(r: dict) -> str:
        if r["explained"]:
            return "explained"
        return "code only" if r["code_level_only"] else "unexplained"

    s2 = [
        '<div class="table-block wide" markdown="1">',
        '<p class="caption"><b>Table S2</b> The '
        f"{f['xt']['cells']} taxon \u00d7 area cells in which Table 1 and the specimen "
        "tables disagree (Additional file 2). <i>Kind</i>: what is "
        "missing. <i>Causes</i>: every cause in the article that applies. <i>Status</i>: "
        "explained, code only (presence agrees under another code) or unexplained. "
        "<i>Link</i>: the discrepancy changes when uncertain site-to-area links are all "
        "unlinked or linked.</p>",
        "",
        "| Accepted name | Area | Kind | Causes | Status | Link | Table 1 codes |",
        "|---|---|---|---|---|---|---|",
        *[
            f"| *{_cell(r['taxon'])}* | {_cell(r['area'])} | "
            + "; ".join(short_kind[k] for k in KINDS if r[k])
            + " | "
            + ("; ".join(short_cause[k] for k in CAUSES if r[k]) or "–")
            + f" | {status(r)} | {'yes' if r['link_dependent'] else ''} | "
            f"{_codes(r['table1_codes'])} |"
            for r in f["xt"]["rows_list"]
        ],
        "",
        "</div>",
    ]
    return "\n".join(['<h2 class="appendix">Appendix</h2>', "", *s1, "", *s2, ""])


def _md_inline(text: str) -> str:
    return markdown.markdown(text).removeprefix("<p>").removesuffix("</p>")


def build(cfg: Config, pdf: bool = True) -> Path:
    root = cfg.root / "paper"
    out = root / "build"
    out.mkdir(parents=True, exist_ok=True)
    f = collect(cfg)
    write_all(f, out / "figures")
    html, _, tracker = render(cfg)
    shutil.copy(root / "style.css", out / "style.css")
    (out / "manuscript.html").write_text(html, encoding="utf-8")
    log.info("[paper] wrote %s (%d references cited)", out / "manuscript.html", len(tracker.used))
    if pdf:
        head = yaml.safe_load((root / "front.yaml").read_text(encoding="utf-8"))["running_head"]
        foot = (
            "Manuscript prepared in the format of Marine Biodiversity Records. Not peer reviewed."
        )
        target = root / "manuscript.pdf"
        _print(root, out / "manuscript.html", target, f"{head} | Page {{page}} of {{pages}}", foot)
        log.info("[paper] wrote %s", target)
    return out / "manuscript.html"


def _print(root: Path, html: Path, pdf: Path, head: str, foot: str, **env: str) -> None:
    subprocess.run(
        ["node", str(root / "print.cjs"), str(html), str(pdf), head, foot],
        check=True,
        env={**os.environ, **env},
    )


def render_preprint(cfg: Config) -> tuple[str, dict, dict]:
    front, body, f, _ = render_parts(cfg)
    env = _env(cfg.root / "paper")
    snapshot = env.filters["longdate"](f["res"]["date_last"])
    html = env.get_template("preprint.html.j2").render(body=body, snapshot=snapshot, **front)
    return html, f, front


def build_preprint(cfg: Config, pdf: bool = True) -> Path:
    """Working-paper layout: one column, figures and tables in place, no journal styling.

    Between the journal-styled layout and the submission DOCX: easy to read and to share,
    without looking like a published article or a submission draft. Same body as both.
    """
    root = cfg.root / "paper"
    out = root / "build"
    out.mkdir(parents=True, exist_ok=True)
    html, f, front = render_preprint(cfg)
    write_all(f, out / "figures")
    shutil.copy(root / "preprint.css", out / "preprint.css")
    (out / "preprint.html").write_text(html, encoding="utf-8")
    log.info("[paper] wrote %s", out / "preprint.html")
    if pdf:
        target = root / "preprint.pdf"
        _print(
            root,
            out / "preprint.html",
            target,
            "",
            f"{front['short_title']} · working paper | {{page}} / {{pages}}",
            PAGE_HEIGHT="297mm",
            MARGIN_TOP="18mm",
            MARGIN_SIDE="22mm",
        )
        log.info("[paper] wrote %s", target)
    return out / "preprint.html"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="anemone_kg paper")
    p.add_argument("--no-pdf", action="store_true")
    p.add_argument(
        "--submission",
        action="store_true",
        help="journal submission files (DOCX, figures as separate files) instead of the layout",
    )
    p.add_argument(
        "--preprint",
        action="store_true",
        help="working-paper layout (one column, figures in place) instead of the journal layout",
    )
    p.add_argument("--config", default=None)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    if args.preprint:
        build_preprint(cfg, pdf=not args.no_pdf)
    elif args.submission:
        from anemone_kg.paper.submission import build_submission

        build_submission(cfg, pdf=not args.no_pdf)
    else:
        build(cfg, pdf=not args.no_pdf)
    return 0
