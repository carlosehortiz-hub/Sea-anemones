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
    assert r["table2"]["fields_agree"] == r["table2"]["fields_checked"]
    assert r["table3"]["fields_agree"] == r["table3"]["fields_checked"]


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
