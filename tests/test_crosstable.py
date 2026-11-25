"""Cross-table review: every W08-W11 flag gets a cause; link sensitivity; evidence tiers."""

from __future__ import annotations

import pandas as pd
import pytest

from anemone_kg.config import load_config
from anemone_kg.dq import crosstable as ct
from anemone_kg.dq.rules import RULES
from anemone_kg.stages.validate import load_tables


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def t(cfg):
    return load_tables(cfg)


@pytest.fixture(scope="module")
def cw(cfg):
    return pd.read_csv(cfg.path("mappings") / "locality_crosswalk.csv")


@pytest.fixture(scope="module")
def review(t, cw):
    return ct.classify(t, cw)


def test_every_flag_has_exactly_one_known_cause(t, review):
    n = sum(len(r.check(t)) for r in RULES if r.rule_id in ct.RULES)
    assert len(review) == n == 33
    assert set(review.cause) <= set(ct.CAUSES)


def test_reidentification_is_found_across_a_misspelt_previous_name(review):
    """Bug once: previous identifications were compared by name-usage id, so the misspelt
    'Homostichantus duerdenii' in Table 3 did not meet 'Homostichanthus duerdeni' in Table 1."""
    r = review[(review.rule == "W10") & (review.taxon == "Homostichanthus duerdeni")]
    assert r.cause.item() == "reidentified"
    assert "Actinoporus elegans" in r.evidence.item()


def test_family_level_voucher_only_explains_taxa_of_that_family(t, review):
    """Bug once: an Actiniidae specimen was offered as the possible voucher of zoantharians."""
    fam = dict(zip(t["taxon"].scientific_name, t["taxon"].family, strict=True))
    above = review[(review.rule == "W08") & (review.cause == "above_species")]
    assert set(above.taxon.map(fam)) == {"Actiniidae"}


def test_no_column_shift_signature(review):
    assert not review.shift_pair.any()


def test_sensitivity_brackets_the_curated_counts(t, cw):
    s = ct.sensitivity(t, cw).set_index("scenario")
    curated = s.loc["as_curated"]
    assert (curated == [13, 7, 5, 8]).all()
    assert s.attrs["uncertain_links"] == 22


def test_relink_changes_only_uncertain_sites(t, cw):
    linked = ct.relink(t, cw, "all_linked")["locality"]
    before = t["locality"].set_index("locality_id").parent_locality_id
    after = linked.set_index("locality_id").parent_locality_id
    changed = before.index[before.fillna("") != after.fillna("")]
    assert len(changed) == 3  # the three links the curator rejected


def test_evidence_tiers_cover_every_assertion(t):
    tiers = ct.evidence_tiers(t)
    assert tiers.notna().all() and len(tiers) == len(t["distribution"])
    counts = tiers.value_counts()
    assert counts["LiteratureRecord"] == 229
    assert counts["SurveyVouchered"] + counts["SurveyUnvouchered"] == 57
    assert counts["MuseumTraced"] + counts["MuseumUntraced"] == 56


def test_cell_support_counts_cells_not_codes(t):
    cells = ct.cell_support(t)
    d = t["distribution"]
    located = d[d.locality_id.notna()]
    assert len(cells) == located.groupby(["taxon_id", "locality_id"]).ngroups
    assert len(cells) < len(located)
