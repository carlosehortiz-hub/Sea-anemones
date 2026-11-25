"""The manuscript: real references, no hand-typed results, figures and tables in order."""

from __future__ import annotations

import re

import pytest

from anemone_kg.config import load_config
from anemone_kg.paper.build import render, render_preprint
from anemone_kg.paper.figures import write_all
from anemone_kg.paper.references import fetch_crossref, load_references, verify


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def rendered(cfg):
    return render(cfg)


@pytest.fixture(scope="module")
def refs(cfg):
    return load_references(cfg.root / "paper" / "references.yaml")


def test_doi_references_match_crossref(cfg, refs):
    records = fetch_crossref(refs, cfg.root / "paper" / "references" / "crossref", offline=True)
    assert len(records) == sum(1 for r in refs.values() if r.doi)
    assert verify(refs, records) == []


def test_reference_list_is_exactly_what_is_cited(rendered, refs):
    _, _, tracker = rendered
    assert set(tracker.used) == set(refs), (
        f"unused: {set(refs) - set(tracker.used)}; unknown: {set(tracker.used) - set(refs)}"
    )


def test_no_template_residue(rendered):
    html, _, _ = rendered
    assert not re.search(r"\{\{|\{%|@@|\bNone\b|\bnan\b", html)


def _first_mentions(html: str, label: str) -> list[int]:
    text = re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")
    seen: list[int] = []
    for m in re.finditer(rf"\b{label}\s+(\d+)", text):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


@pytest.mark.parametrize("label", ["Fig.", "Table"])
def test_figures_and_tables_are_numbered_in_order_of_appearance(rendered, label):
    """Bug once: Fig. 2 appeared before Fig. 1. Captions and mentions must be ordered."""
    html, _, _ = rendered
    caption_nums = [
        int(n)
        for n in re.findall(rf'class="caption"><b>{re.escape(label)}(?:&nbsp;| )(\d+)</b>', html)
    ]
    assert caption_nums == list(range(1, len(caption_nums) + 1))
    body = html.split('class="body"', 1)[1].split("<h2>References</h2>")[0]
    mentions = [n for n in _first_mentions(body, re.escape(label)) if n <= len(caption_nums)]
    assert mentions == sorted(mentions), f"{label} first mentioned out of order: {mentions}"


def test_headline_numbers_come_from_the_pipeline(rendered):
    html, f, _ = rendered
    text = re.sub(r"<[^>]+>", " ", html)
    assert f"{f['graph']['triples']:,} triples" in text
    assert f"WoRMS ({f['res']['worms']['accepted']}/{f['res']['n_taxa']})" in text
    assert f"{f['dq']['schema_checks']} column-level checks" in text


def test_manuscript_is_not_presented_as_a_published_article(rendered):
    """No masthead, DOI of its own, or publisher branding; it says it is a manuscript."""
    html, _, _ = rendered
    assert "not peer reviewed" in html
    assert "BioMed Central" not in html and "CrossMark" not in html


def test_figures_are_generated(cfg, rendered, tmp_path):
    _, f, _ = rendered
    paths = write_all(f, tmp_path)
    for p in paths.values():
        svg = p.read_text()
        assert svg.startswith("<?xml") or svg.startswith("<svg")
        assert "nan" not in svg


def test_preprint_layout_is_complete_and_unbranded(cfg, rendered):
    """The working-paper layout carries the same body, all figures, and no journal styling."""
    html, _, _ = render_preprint(cfg)
    layout, _, _ = rendered
    assert not re.search(r"\{\{|\{%|@@|\bNone\b|\bnan\b", html)
    assert html.count('class="figure') == layout.count('class="figure') == 4
    assert html.count('class="table-block') == layout.count('class="table-block') == 7  # 5 + S1, S2
    assert 'class="banner"' in layout and 'class="banner"' not in html
    assert "column-count" not in (cfg.root / "paper" / "preprint.css").read_text()
    assert "not peer reviewed" in html
