"""Extraction census: a second, independent reading of Tables 1-3, and its positive controls.

Every other check would pass a code read into the wrong cell. These tests show that the
second reading (Poppler, separate parser) agrees with the extraction everywhere, and that it
catches each class of extraction error a reviewer named: a column shift, a value read into
the wrong row, two columns swapped, a changed digit.
"""

from __future__ import annotations

import shutil

import pandas as pd
import pytest

from anemone_kg.audit.second_reading import (
    TABLE2_FIELDS,
    TABLE3_FIELDS,
    audit,
    compare_fixed,
    compare_table1,
    n_disagreements,
    read_table1,
)
from anemone_kg.config import load_config

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler missing")


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def interim(cfg):
    d = cfg.path("interim")

    def fixed(name):
        return pd.read_csv(d / name, dtype=str).assign(
            no=lambda x: x.no.astype(int), source_page=lambda x: x.source_page.astype(int)
        )

    return {
        "t1": pd.read_csv(d / "table1_cells.csv"),
        "t2": fixed("table2_specimens.csv"),
        "t3": fixed("table3_mohbr_specimens.csv"),
    }


@pytest.fixture(scope="module")
def second_t1(cfg):
    return read_table1(cfg.pdf)


def test_census_agrees_everywhere(cfg):
    r = audit(cfg.pdf, cfg.path("interim"))
    assert n_disagreements(r) == 0
    assert r["table1"]["cells_agree"] == r["table1"]["cells_first"] == 263
    assert r["table1"]["codes_agree"] == 344
    assert r["table2"]["fields_agree"] == r["table2"]["fields_checked"] == 128 * 8
    assert r["table3"]["fields_agree"] == r["table3"]["fields_checked"] == 84 * 7


def test_detects_a_code_shifted_to_the_next_column(interim, second_t1):
    m = interim["t1"].copy()
    i = m.index[m.locality_col_id == "T1A02"][0]
    m.loc[i, "locality_col_id"] = "T1A03"
    assert len(compare_table1(m, second_t1)["disagreements"]) == 2


def test_detects_a_code_moved_to_another_row(interim, second_t1):
    m = interim["t1"].copy()
    m.loc[0, "row_no"] = int(m.loc[0, "row_no"]) + 1
    assert compare_table1(m, second_t1)["disagreements"]


def test_detects_swapped_columns(cfg, interim):
    m = interim["t3"].copy()
    r = m.index[m.previous_identification != m.current_identification][0]
    m.loc[r, ["previous_identification", "current_identification"]] = m.loc[
        r, ["current_identification", "previous_identification"]
    ].values
    assert compare_fixed(m, TABLE3_FIELDS, cfg.pdf)["disagreements"]


def test_detects_a_value_read_from_another_row(cfg, interim):
    t = interim["t2"]
    m = t.copy()
    m.loc[0, "verbatim_species"], m.loc[5, "verbatim_species"] = (
        t.loc[5, "verbatim_species"],
        t.loc[0, "verbatim_species"],
    )
    assert len(compare_fixed(m, TABLE2_FIELDS, cfg.pdf)["disagreements"]) == 2


def test_detects_a_changed_coordinate_digit(cfg, interim):
    m = interim["t2"].copy()
    m.loc[3, "verbatim_latitude"] = m.loc[3, "verbatim_latitude"].replace("2.51", "2.15")
    assert compare_fixed(m, TABLE2_FIELDS, cfg.pdf)["disagreements"]


def test_detects_a_value_moved_into_the_adjacent_field(cfg, interim):
    """Round-2 finding: token containment could not see a value that slid into a
    neighbouring empty field. The aligned comparison checks each column band."""
    m = interim["t3"].copy()
    m.loc[0, "verbatim_date"] = f"{m.loc[0, 'verbatim_locality']} {m.loc[0, 'verbatim_date']}"
    m.loc[0, "verbatim_locality"] = ""
    assert len(compare_fixed(m, TABLE3_FIELDS, cfg.pdf)["disagreements"]) == 2


# ----------------------------------------------------------- rendered-image check


@pytest.fixture(scope="module")
def ink(cfg):
    from anemone_kg.audit.rendered import ink_census

    return ink_census(cfg.pdf, cfg.path("interim"))


def test_rendered_check_agrees_on_every_cell(ink):
    assert ink["cells"] == 52 * 27
    assert ink["ink_and_code"] == 263 and ink["no_ink_no_code"] == 52 * 27 - 263
    assert not ink["ink_without_code"] and not ink["code_without_ink"]
    assert ink["separated"]


def test_rendered_check_finds_a_missed_and_an_invented_code(cfg, tmp_path):
    """Positive controls: drop a code from the extraction (a missed code, the signature of a
    'specimen without a code'), and add one to an empty cell."""
    from anemone_kg.audit.rendered import ink_census

    cells = pd.read_csv(cfg.path("interim") / "table1_cells.csv")
    first = cells.iloc[0]
    mutated = cells[
        ~((cells.row_no == first.row_no) & (cells.locality_col_id == first.locality_col_id))
    ]
    invented = first.copy()
    invented["locality_col_id"] = "T1A01" if first.locality_col_id != "T1A01" else "T1A03"
    mutated = pd.concat([mutated, invented.to_frame().T])
    mutated.to_csv(tmp_path / "table1_cells.csv", index=False)
    r = ink_census(cfg.pdf, tmp_path)
    assert len(r["ink_without_code"]) == 1 and len(r["code_without_ink"]) == 1


# ------------------------------------------------- the parser's own fail-loudly checks


def _patched_words(monkeypatch, mutate):
    from anemone_kg.extract import tables

    real = tables._words

    def fake(page):
        return mutate(page, real(page))

    monkeypatch.setattr(tables, "_words", fake)
    return tables


def test_parser_raises_on_a_broken_row_sequence(cfg, monkeypatch):
    def drop_row_7(page, words):
        return [w for w in words if not (w["text"] == "7" and w["x0"] < 72)]

    tables = _patched_words(monkeypatch, drop_row_7)
    with pytest.raises(tables.ExtractionError):
        tables.extract_table1(cfg.pdf)


def test_parser_raises_on_an_unknown_code(cfg, monkeypatch):
    def bad_code(page, words):
        out = []
        done = False
        for w in words:
            if not done and w["text"] == "a" and w["x0"] > 150:
                w = {**w, "text": "z"}
                done = True
            out.append(w)
        return out

    tables = _patched_words(monkeypatch, bad_code)
    with pytest.raises(tables.ExtractionError):
        tables.extract_table1(cfg.pdf)


def test_parser_raises_on_an_unexpected_column_count(cfg, monkeypatch):
    def drop_header(page, words):
        return [w for w in words if w["text"] != "Collector"]

    tables = _patched_words(monkeypatch, drop_header)
    with pytest.raises(tables.ExtractionError):
        tables.extract_fixed_table(cfg.pdf, tables.TABLE3)
