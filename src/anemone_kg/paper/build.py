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
    root = cfg.root / "paper"
    f = collect(cfg)
    refs = load_references(root / "references.yaml")
    records = fetch_crossref(refs, root / "references" / "crossref", offline=True)
    problems = verify(refs, records)
    if problems:
        raise ValueError("references do not match Crossref: " + "; ".join(problems))
    tracker = CitationTracker(refs)
    env = _env(root)
    ctx = {"f": f, "cite": tracker.cite, "citet": tracker.citet, "references": "@@REFS@@"}

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
    html = env.get_template("template.html.j2").render(body=body, **front)
    return html, f, tracker


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
        target = root / "manuscript.pdf"
        subprocess.run(
            ["node", str(root / "print.cjs"), str(out / "manuscript.html"), str(target), head],
            check=True,
        )
        log.info("[paper] wrote %s", target)
    return out / "manuscript.html"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="anemone_kg paper")
    p.add_argument("--no-pdf", action="store_true")
    p.add_argument("--config", default=None)
    args = p.parse_args(argv)
    build(load_config(args.config), pdf=not args.no_pdf)
    return 0
