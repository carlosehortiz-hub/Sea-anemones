"""The journal submission version: same text as the layout, arranged as the journal asks."""

from __future__ import annotations

import re
import shutil
import zipfile
from collections import Counter

import pytest

from anemone_kg.config import load_config
from anemone_kg.paper.build import render_parts
from anemone_kg.paper.submission import PAGEBREAK, submission_html, to_docx

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def sub(cfg):
    return submission_html(cfg)


@pytest.fixture(scope="module")
def docx_xml(cfg, sub, tmp_path_factory):
    html, _, f = sub
    out = tmp_path_factory.mktemp("sub") / "m.docx"
    to_docx(html, out, f["res"]["date_last"])
    with zipfile.ZipFile(out) as z:
        return {n: z.read(n).decode() for n in z.namelist() if n.endswith(".xml")}, out


def _words(html: str) -> Counter:
    return Counter(
        re.sub(r"<[^>]+>", " ", html.replace("&nbsp;", " ")).replace("\u00a0", " ").split()
    )


def test_same_text_as_the_layout(cfg, sub):
    """Only the arrangement may differ: every word of the layout's body is in the submission."""
    _, body, _, _ = render_parts(cfg)
    html, _, _ = sub
    body = body.split('<h2 class="appendix">')[0]  # the appendix goes as additional files
    assert not (_words(body) - _words(html))


def test_figures_out_of_the_text_and_legends_after_references(sub):
    html, figures, _ = sub
    assert "<img" not in html
    assert [s for s, _ in figures] == [
        "fig1_pipeline",
        "fig2_model",
        "fig3_resolution",
        "fig4_evidence",
    ]
    refs, figs, tabs = (html.index(h) for h in ("<h2>References", "<h2>Figures", "<h2>Tables"))
    assert refs < figs < tabs
    for i in range(1, 6):
        assert html.index(f"<b>Table\u00a0{i}</b>") > tabs


def test_docx_layout(docx_xml):
    xml, _ = docx_xml
    doc, styles = xml["word/document.xml"], xml["word/styles.xml"]
    assert '<w:lnNumType w:countBy="1"' in doc
    assert 'r:id="rIdPageNumbers"' in doc and " PAGE " in xml["word/footer-pages.xml"]
    assert "<w:suppressLineNumbers/>" in xml["word/footer-pages.xml"]
    assert PAGEBREAK not in doc
    assert doc.count("<w:pageBreakBefore/>") >= 7  # abstract, body, figures, tables, 4 tables
    assert 'w:line="480"' in styles and "<w:color " not in styles
    assert doc.count("<w:tbl>") == 6


def test_docx_is_reproducible(cfg, sub, docx_xml, tmp_path):
    """pandoc stamps the build time into docProps unless SOURCE_DATE_EPOCH pins it."""
    html, _, f = sub
    _, first = docx_xml
    again = tmp_path / "again.docx"
    to_docx(html, again, f["res"]["date_last"])
    assert first.read_bytes() == again.read_bytes()
