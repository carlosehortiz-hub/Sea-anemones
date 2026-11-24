"""Journal submission files: the same text as the layout, arranged the way the journal asks.

    python -m anemone_kg paper --submission           # DOCX + PDF preview + figure files
    python -m anemone_kg paper --submission --no-pdf  # DOCX + figure files only

A journal receives an editable manuscript, not a typeset page. Following the BMC instructions
that Marine Biodiversity Records uses, and the structure of the source article (same journal):

* one column, double line spacing, continuous line numbers, page numbers in the footer;
* a title page with every author, affiliation and e-mail address;
* a structured abstract (Background, Results, Conclusions) and keywords;
* figures uploaded as separate files, with their titles and legends listed after the
  references;
* tables at the end of the manuscript file, one per page, each with its title above it.

The rules were applied as the author knows them. The journal's web page could not be reached
from the build environment, so check them against its current instructions before submitting.

The body is `build.render_parts`, the same HTML that the two-column layout uses. Only its
arrangement changes, so the two versions cannot say different things.

The DOCX is reproducible: pandoc is run with SOURCE_DATE_EPOCH set to the resolution date, and
the archive is rewritten with fixed timestamps.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from anemone_kg.config import Config
from anemone_kg.paper.build import render_parts
from anemone_kg.paper.facts import collect
from anemone_kg.paper.figures import write_all

log = logging.getLogger(__name__)

PAGEBREAK = "@@PAGEBREAK@@"
FONT = "Times New Roman"
_FIG = re.compile(r'<div class="figure[^"]*">(.*?)</div>', re.S)
_TAB = re.compile(r'<div class="table-block[^"]*">(.*?)</div>', re.S)
_CAPTION = re.compile(r'<p class="caption">(.*?)</p>', re.S)
_IMG = re.compile(r'<img src="figures/([^"]+)\.svg"')


def _break() -> str:
    return f"<p>{PAGEBREAK}</p>"


def submission_html(cfg: Config) -> tuple[str, list[tuple[str, str]], dict]:
    """HTML for pandoc, plus (figure file stem, legend) in order of appearance."""
    front, body, f, _ = render_parts(cfg)

    figures: list[tuple[str, str]] = []
    for block in _FIG.findall(body):
        stem = _IMG.search(block).group(1)
        figures.append((stem, _CAPTION.search(block).group(1).strip()))
    tables = []
    for block in _TAB.findall(body):
        caption = _CAPTION.search(block).group(1).strip()
        tables.append((caption, _CAPTION.sub("", block, count=1).strip()))
    body = _FIG.sub("", body)
    body = _TAB.sub("", body)

    main, refs = body.split("<h2>References</h2>", 1)
    legends = "".join(f"<p>{cap}</p>" for _, cap in figures)
    tail = "".join(f"{_break()}<p>{cap}</p>{table}" for cap, table in tables)

    a = front["abstract"]
    html = (
        f"<h1>{front['title'].strip()}</h1>"
        f"<p>{front['authors']}</p>"
        f"{front['affiliations']}"
        f"{_break()}"
        "<h2>Abstract</h2>"
        f"<p><b>Background:</b> {a['background']}</p>"
        f"<p><b>Results:</b> {a['results']}</p>"
        f"<p><b>Conclusions:</b> {a['conclusions']}</p>"
        f"<p><b>Keywords:</b> {front['keywords']}</p>"
        f"{_break()}"
        f"{main}"
        f"<h2>References</h2>{refs}"
        f"{_break()}<h2>Figures</h2>{legends}"
        f"{_break()}<h2>Tables</h2>{tail.removeprefix(_break())}"
    )
    html = html.replace("&nbsp;", "\u00a0")
    return f'<html><head><meta charset="utf-8"></head><body>{html}</body></html>', figures, f


# ---------------------------------------------------------------- DOCX post-processing


def _styles(xml: str) -> str:
    """Times 12 pt, black, double spacing; single spacing inside tables only."""
    fonts = f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" w:cs="{FONT}"/>'
    xml = re.sub(r"<w:rFonts [^>]*/>", fonts, xml)
    xml = re.sub(r"<w:color [^>]*/>", "", xml)
    xml = re.sub(
        r"<w:spacing [^>]*/>",
        '<w:spacing w:before="0" w:after="0" w:line="480" w:lineRule="auto"/>',
        xml,
    )
    xml = re.sub(r"(<w:rPrDefault>\s*<w:rPr>)", r'\1<w:sz w:val="24"/><w:szCs w:val="24"/>', xml)
    table_text = (
        '<w:style w:type="paragraph" w:customStyle="1" w:styleId="TableText">'
        '<w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/></w:pPr>'
        '<w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>'
    )
    return xml.replace("</w:styles>", table_text + "</w:styles>")


TEXT_WIDTH = 11906 - 2 * 1418  # A4 width minus 2.5 cm margins, in twentieths of a point


def _text(xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


def _table(m: re.Match) -> str:
    """Full text width; columns weighted by their content; single-spaced cells."""
    t = m.group(0)
    rows = [
        re.findall(r"<w:tc>.*?</w:tc>", r, re.S) for r in re.findall(r"<w:tr>.*?</w:tr>", t, re.S)
    ]
    ncol = max(len(r) for r in rows)
    weight = [1.0] * ncol
    for j in range(ncol):
        texts = [_text(r[j]) for r in rows if j < len(r)]
        longest_word = max((len(w) for x in texts for w in x.split()), default=4)
        mean = sum(len(x) for x in texts) / max(len(texts), 1)
        weight[j] = max(longest_word, min(mean, 45), 4)
    widths = [int(TEXT_WIDTH * w / sum(weight)) for w in weight]
    grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
    t = re.sub(r"<w:tblGrid>.*?</w:tblGrid>", grid, t, flags=re.S)
    t = re.sub(r"<w:tblW [^>]*/>", f'<w:tblW w:type="dxa" w:w="{TEXT_WIDTH}"/>', t)
    t = re.sub(r"<w:jc w:val=\"start\" ?/>(</w:tblPr>)", r'<w:tblLayout w:type="fixed"/>\1', t)

    def cell(row: str) -> str:
        cells = iter(widths)
        return re.sub(
            r"<w:tcPr ?/>|<w:tcPr>",
            lambda c: (
                f'<w:tcPr><w:tcW w:type="dxa" w:w="{next(cells)}"/>'
                + ("</w:tcPr>" if c.group(0) != "<w:tcPr>" else "")
            ),
            row,
        )

    t = re.sub(r"<w:tr>.*?</w:tr>", lambda r: cell(r.group(0)), t, flags=re.S)
    t = re.sub(r'<w:pStyle w:val="[^"]+" ?/>', '<w:pStyle w:val="TableText"/>', t)
    return re.sub(r"<w:p>(?!<w:pPr>)", '<w:p><w:pPr><w:pStyle w:val="TableText"/></w:pPr>', t)


def _document(xml: str) -> str:
    """Page breaks, tables, A4, line numbers and a page-number footer."""
    # A page break is a property of the next paragraph, not a paragraph of its own: an empty
    # break paragraph at the foot of a full page would produce a blank page.
    token = (
        r"<w:p>(?:(?!</w:p>).)*" + PAGEBREAK + r"(?:(?!</w:p>).)*</w:p>\s*"
        r"((?:<w:bookmark(?:Start|End)[^>]*/>\s*)*)"
    )
    xml = re.sub(token + r"<w:p><w:pPr>", r"\1<w:p><w:pPr><w:pageBreakBefore/>", xml, flags=re.S)
    xml = re.sub(token + r"<w:p>", r"\1<w:p><w:pPr><w:pageBreakBefore/></w:pPr>", xml, flags=re.S)
    if PAGEBREAK in xml:
        raise ValueError("a page break was not followed by a paragraph")
    xml = re.sub(r"<w:tbl>.*?</w:tbl>", _table, xml, flags=re.S)
    sect = (
        '<w:sectPr><w:footerReference w:type="default" r:id="rIdPageNumbers"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" w:header="709" '
        'w:footer="709" w:gutter="0"/>'
        '<w:lnNumType w:countBy="1" w:distance="284" w:restart="continuous"/>'
        "</w:sectPr>"
    )
    xml, n = re.subn(r"<w:sectPr\b.*?</w:sectPr>|<w:sectPr\b[^>]*/>", sect, xml, flags=re.S)
    if n == 0:
        xml = xml.replace("</w:body>", sect + "</w:body>")
    return xml


_FOOTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:p><w:pPr><w:suppressLineNumbers/><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
)


def _postprocess(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src) as zin:
        items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    out: list[tuple[str, bytes]] = []
    for name, data in items:
        if name == "word/styles.xml":
            data = _styles(data.decode()).encode()
        elif name == "word/document.xml":
            data = _document(data.decode()).encode()
        elif name == "word/_rels/document.xml.rels":
            rel = (
                '<Relationship Id="rIdPageNumbers" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/footer" Target="footer-pages.xml"/>'
            )
            data = data.decode().replace("</Relationships>", rel + "</Relationships>").encode()
        elif name == "[Content_Types].xml":
            ct = (
                '<Override PartName="/word/footer-pages.xml" ContentType="application/'
                'vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            )
            data = data.decode().replace("</Types>", ct + "</Types>").encode()
        out.append((name, data))
    out.append(("word/footer-pages.xml", _FOOTER.encode()))
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in out:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, data)


def to_docx(html: str, dst: Path, date_iso: str) -> None:
    epoch = int(datetime.fromisoformat(date_iso).replace(tzinfo=UTC).timestamp())
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch)}
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "in.html").write_text(html, encoding="utf-8")
        ref = t / "reference.docx"
        with ref.open("wb") as fh:
            subprocess.run(
                ["pandoc", "--print-default-data-file", "reference.docx"],
                stdout=fh,
                check=True,
            )
        raw = t / "raw.docx"
        subprocess.run(
            [
                "pandoc",
                "-f",
                "html",
                "-t",
                "docx",
                "--reference-doc",
                str(ref),
                "-o",
                str(raw),
                str(t / "in.html"),
            ],
            check=True,
            env=env,
        )
        _postprocess(raw, dst)


def build_submission(cfg: Config, pdf: bool = True) -> Path:
    root = cfg.root / "paper"
    out = root / "submission"
    shutil.rmtree(out, ignore_errors=True)
    (out / "figures").mkdir(parents=True)

    html, figures, f = submission_html(cfg)
    docx = out / "manuscript.docx"
    to_docx(html, docx, f["res"]["date_last"])
    log.info("[paper] wrote %s", docx)

    with tempfile.TemporaryDirectory() as tmp:
        svgs = {p.stem: p for p in write_all(collect(cfg), Path(tmp)).values()}
        jobs = []
        for i, (stem, _) in enumerate(figures, 1):
            jobs += [str(svgs[stem]), str(out / "figures" / f"Fig{i}")]
        subprocess.run(["node", str(root / "export_figures.cjs"), *jobs], check=True)
    log.info("[paper] wrote %d figures (PDF and PNG) to %s", len(figures), out / "figures")

    if pdf:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out), str(docx)],
            check=True,
            capture_output=True,
        )
        log.info("[paper] wrote %s (preview of the DOCX)", out / "manuscript.pdf")
    return docx
