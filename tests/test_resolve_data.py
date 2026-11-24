"""Resolution outputs, rebuilt offline from the committed cache."""

from __future__ import annotations

import pandas as pd
import pytest
from linkml_runtime.utils.schemaview import SchemaView

from anemone_kg.config import load_config
from anemone_kg.stages.resolve import make_http, resolve_all

TABLES = {
    "taxon_mapping": "TaxonMapping",
    "worms_record": "WormsRecord",
    "habitat_annotation": "HabitatAnnotation",
}


@pytest.fixture(scope="module")
def built(monkeypatch_module):
    cfg = load_config()
    http = make_http(cfg)
    assert http.offline
    return resolve_all(cfg, http), http


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    mp.setenv("ANEMONE_KG_OFFLINE", "1")
    yield mp
    mp.undo()


def test_rebuild_from_cache_needs_no_network(built):
    _, http = built
    assert http.stats["network"] == 0 and http.stats["miss"] == 0


def test_committed_outputs_match_rebuild(built):
    cfg = load_config()
    for name, df in built[0].items():
        committed = pd.read_csv(cfg.path("processed") / "canonical" / f"{name}.csv")
        rebuilt = pd.read_csv(pd.io.common.StringIO(df.to_csv(index=False)))
        pd.testing.assert_frame_equal(committed, rebuilt, obj=name)


@pytest.mark.parametrize(("table", "cls"), TABLES.items())
def test_schema_contract(built, table, cls):
    sv = SchemaView(str(load_config().root / "schema" / "anemone_kg.yaml"))
    df = built[0][table]
    slots = sv.class_induced_slots(cls)
    assert set(df.columns) == {s.name for s in slots}
    for s in slots:
        if s.identifier:
            assert df[s.name].notna().all() and df[s.name].is_unique, s.name
        elif s.required:
            assert df[s.name].notna().all(), s.name


def test_one_row_per_taxon_and_service(built):
    m = built[0]["taxon_mapping"]
    taxa = pd.read_csv(load_config().path("processed") / "canonical" / "taxon.csv")
    assert len(m) == 3 * len(taxa)
    assert (m.groupby("subject_id").object_source.nunique() == 3).all()


def test_only_accepted_rows_assert_a_mapping(built):
    m = built[0]["taxon_mapping"]
    assert m.loc[m.status == "accepted", "predicate_id"].notna().all()
    assert m.loc[m.status != "accepted", "predicate_id"].isna().all()


def test_known_resolutions(built):
    m = built[0]["taxon_mapping"].set_index(["subject_label", "object_source"])
    w = built[0]["worms_record"].set_index("aphia_id")
    ap = m.loc[("Aiptasia pallida", "worms")]
    assert ap.object_id == "worms:283486" and ap.match_type == "exact_synonym"
    assert w.loc[283486, "valid_aphia_id"] == 1264073
    assert 1264073 in w.index  # the accepted name exists as its own record
    zs = m.loc[("Zoanthus sociatus", "worms")]
    assert zs.object_id == "worms:288843" and "authority" in zs.comment
    assert m.loc[("Ceriantheomorphe brasiliensis", "worms")].status == "ambiguous"


def test_habitat_annotations(built):
    a = built[0]["habitat_annotation"]
    assert set(a.status) <= {"accepted", "unresolved", "negated"}
    neg = a[a.status == "negated"]
    assert set(neg.envo_label) == {"intertidal zone"} and len(neg) == 2
    assert a.loc[a.status == "accepted", "envo_id"].str.match(r"^ENVO:\d{8}$").all()
    assert (a.loc[a.envo_label == "coral rubble", "status"] == "unresolved").all()
