"""Extraction tests against the real source PDF.

Expected values were read from the page images of the paper, independently of
the parser. They pin the behaviour so that a layout regression is caught.
"""

from __future__ import annotations

import pandas as pd
import pytest

from anemone_kg.config import load_config
from anemone_kg.stages.extract import run_extraction

COORD = r"^\d{1,2}° ?\d{1,2}’ \d{1,2}(\.\d+)?”$"


@pytest.fixture(scope="session")
def frames() -> dict[str, pd.DataFrame]:
    return run_extraction(load_config().pdf)


def _cell(frames, row_no: int, locality: str) -> str | None:
    c = frames["table1_cells"].merge(frames["table1_localities"], on="locality_col_id")
    hit = c[(c.row_no == row_no) & (c.verbatim_locality == locality)]
    return None if hit.empty else hit["cell_verbatim"].iloc[0]


def test_row_counts_match_the_paper(frames):
    """The paper states 128 collected and 84 MOHBR specimens, and 26 species."""
    assert len(frames["table1_taxa"]) == 52
    assert len(frames["table1_localities"]) == 27
    assert len(frames["table2_specimens"]) == 128
    assert len(frames["table3_mohbr_specimens"]) == 84
    assert len(frames["species_accounts"]) == 26


def test_sampled_localities_come_from_bold_headers(frames):
    loc = frames["table1_localities"]
    assert loc["sampled_in_study"].sum() == 6
    assert set(loc.loc[loc.sampled_in_study, "verbatim_locality"]) >= {
        "Morrocoy National Park",
        "Archipiélago Los Roques National Park",
    }


@pytest.mark.parametrize(
    ("row_no", "locality", "expected"),
    [
        (3, "Morrocoy National Park", "a, e, *"),
        (13, "Morrocoy National Park", "a, e, g, *"),
        (13, "Isla de Pájaros, Maracaibo", "e"),
        (7, "Morrocoy National Park", "*, N"),
        (31, "Mochima National Park", "*, N"),
        (3, "Laguna de la Restinga (Isla de Margarita)", "a, j, *"),
        (3, "Isla La Blanquilla", "a"),
        (2, "Mochima National Park", None),
    ],
)
def test_table1_cells_match_page_images(frames, row_no, locality, expected):
    assert _cell(frames, row_no, locality) == expected


def test_new_records_are_the_two_in_the_abstract(frames):
    c = frames["table1_cells"].merge(frames["table1_taxa"], on="row_no")
    assert set(c.loc[c.code == "N", "name_text"]) == {"Anthopleura pallida", "Telmatactis vernonia"}


def test_raised_dagger_does_not_duplicate_rows(frames):
    """Bug: '†' sits ~2 pt above the baseline and was read as a second row 5."""
    taxa = frames["table1_taxa"]
    assert taxa["row_no"].is_unique
    row5 = taxa.set_index("row_no").loc[5]
    assert row5["verbatim_name"] == "Anthopleura cascaia †"
    assert row5["flag_invalid"]


def test_family_authority_overrun_is_not_read_as_cell(frames):
    """Bug: 'Family Boloceroididae Carlgren, 1924b' runs into column 1 and was parsed as codes."""
    taxa = frames["table1_taxa"].set_index("row_no")
    assert taxa.loc[26, "verbatim_family"] == "Family Boloceroididae Carlgren, 1924b"
    assert set(frames["table1_cells"]["code"]) <= set("abcdefghij*N")


def test_legend_lists_all_ten_sources(frames):
    leg = frames["table1_legend"]
    assert list(leg.loc[leg.kind == "source", "code"]) == list("abcdefghij")
    assert leg.set_index("code").loc["e", "meaning"] == "Agudo (1987)"


def test_coordinates_keep_raised_prime_marks(frames):
    """Bug: prime/second marks were read before the numbers (line order by 'top')."""
    t2 = frames["table2_specimens"]
    assert t2["verbatim_latitude"].str.match(COORD).all()
    assert t2["verbatim_longitude"].str.match(COORD).all()
    assert t2.loc[0, "verbatim_latitude"] == "10° 53’ 2.51”"


def test_extraction_is_verbatim(frames):
    """Typos are kept at this stage; correction is a logged canonicalisation step."""
    t2 = frames["table2_specimens"].set_index("no")
    assert t2.loc[25, "verbatim_species"] == "Phymantus crucifer"
    t3 = frames["table3_mohbr_specimens"].set_index("no")
    assert t3.loc[73, "verbatim_date"] == "31/04/2012"
    assert pd.isna(t3.loc[59, "verbatim_state"]) or t3.loc[59, "verbatim_state"] == ""


def test_species_accounts_ranks_and_habitat(frames):
    acc = frames["species_accounts"].set_index("name_text")
    assert acc.loc["Anemonia sargassensis", "verbatim_family"].startswith("Family ACTINIIDAE")
    assert acc.loc["Parazoanthus swiftii", "verbatim_family"].endswith("1901")
    assert acc.loc["Bunodeopsis antilliensis", "habitat_text"].startswith(
        "This species lives attached to seagrass leaves"
    )
    assert (acc["source_page"].between(2, 25)).all()


def test_every_row_has_a_source_locator(frames):
    for name, df in frames.items():
        assert {"source_page", "source_ref"} <= set(df.columns), name
        assert df["source_ref"].notna().all(), name
