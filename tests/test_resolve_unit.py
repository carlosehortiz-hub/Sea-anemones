"""Resolver logic with mocked HTTP - no network, every branch of the acceptance policy."""

from __future__ import annotations

import pandas as pd
import pytest
import requests
import responses

from anemone_kg.resolve.habitats import EnvoLookup, annotate
from anemone_kg.resolve.http import CachedHttp, CacheMiss
from anemone_kg.resolve.taxa import (
    GBIF,
    NCBI,
    WORMS,
    Override,
    TaxonResolver,
    normalise_authority,
)


def rec(
    aphia,
    name,
    authority="X, 1900",
    status="accepted",
    valid=None,
    phylum="Cnidaria",
    rank="Species",
    match_type="exact",
):
    valid = valid or (aphia, name)
    return {
        "AphiaID": aphia,
        "scientificname": name,
        "authority": authority,
        "status": status,
        "unacceptreason": None,
        "valid_AphiaID": valid[0],
        "valid_name": valid[1],
        "rank": rank,
        "phylum": phylum,
        "order": "Actiniaria",
        "family": "Actiniidae",
        "lsid": f"urn:lsid:marinespecies.org:taxname:{aphia}",
        "url": f"https://www.marinespecies.org/aphia.php?p=taxdetails&id={aphia}",
        "match_type": match_type,
    }


@pytest.fixture
def http(tmp_path, monkeypatch):
    monkeypatch.delenv("ANEMONE_KG_OFFLINE", raising=False)
    return CachedHttp(tmp_path, "test-agent", min_interval_s=0)


def by_name(name):
    return f"{WORMS}/AphiaRecordsByName/{name}"


# ------------------------------------------------------------------- cache
@responses.activate
def test_cache_hit_avoids_second_request(http):
    responses.get(by_name("A b"), json=[rec(1, "A b")])
    first = http.get("worms", by_name("A b"))
    second = http.get("worms", by_name("A b"))
    assert len(responses.calls) == 1
    assert first.body == second.body and first.cache_key == second.cache_key
    assert http.stats == {"hit": 1, "miss": 1, "network": 1}


@responses.activate
def test_204_is_cached_as_empty_body(http):
    responses.get(by_name("Nope nope"), status=204)
    assert http.get("worms", by_name("Nope nope")).body is None
    assert http.get("worms", by_name("Nope nope")).status_code == 204


@responses.activate
def test_server_error_is_not_cached(http):
    responses.get(by_name("Err err"), status=500)
    with pytest.raises(requests.HTTPError):
        http.get("worms", by_name("Err err"))
    assert not list(http.root.rglob("*.json"))


def test_offline_miss_raises_instead_of_guessing(tmp_path, monkeypatch):
    monkeypatch.setenv("ANEMONE_KG_OFFLINE", "1")
    with pytest.raises(CacheMiss):
        CachedHttp(tmp_path, "t").get("worms", by_name("A b"))


# ------------------------------------------------------------------- WoRMS
@responses.activate
def test_worms_exact_synonym_fetches_accepted_record(http):
    responses.get(
        by_name("Aiptasia pallida"),
        json=[rec(10, "Aiptasia pallida", status="unaccepted", valid=(20, "Exaiptasia diaphana"))],
    )
    responses.get(f"{WORMS}/AphiaRecordByAphiaID/20", json=rec(20, "Exaiptasia diaphana"))
    r = TaxonResolver(http)
    m = r.worms("t1", "Aiptasia pallida", "species")
    assert (m.status, m.match_type, m.object_id) == ("accepted", "exact_synonym", "worms:10")
    assert set(r.worms_records) == {10, 20}


@responses.activate
def test_worms_homonym_resolved_by_printed_authority(http):
    responses.get(
        by_name("Zoanthus sociatus"),
        json=[
            rec(1, "Zoanthus sociatus", "(Ellis, 1768)"),
            rec(2, "Zoanthus sociatus", "Le Sueur, 1818", status="taxon inquirendum"),
        ],
    )
    m = TaxonResolver(http).worms("t", "Zoanthus sociatus", "species", "(Ellis, 1768)")
    assert (m.status, m.object_id) == ("accepted", "worms:1")
    assert "resolved by authority" in m.comment


@responses.activate
def test_worms_homonym_without_authority_stays_ambiguous(http):
    responses.get(by_name("C b"), json=[rec(1, "C b", "A, 1919"), rec(2, "C b", "B, 1931")])
    m = TaxonResolver(http).worms("t", "C b", "species", None)
    assert m.status == "ambiguous" and m.object_id is None


@responses.activate
def test_worms_other_phylum_homonym_is_ignored(http):
    responses.get(by_name("A b"), json=[rec(1, "A b"), rec(2, "A b", phylum="Mollusca")])
    assert TaxonResolver(http).worms("t", "A b", "species").object_id == "worms:1"


@responses.activate
def test_worms_fuzzy_is_candidate_never_identifier(http):
    responses.get(by_name("Homostichantus duerdenii"), status=204)
    responses.get(
        f"{WORMS}/AphiaRecordsByMatchNames",
        json=[[rec(5, "Homostichanthus duerdeni", match_type="phonetic")]],
    )
    m = TaxonResolver(http).worms("t", "Homostichantus duerdenii", "species")
    assert m.status == "candidate" and m.predicate_id is None
    assert m.confidence == 0.8


@responses.activate
def test_curator_override_accepts_candidate(http):
    responses.get(by_name("Homostichantus duerdenii"), status=204)
    responses.get(
        f"{WORMS}/AphiaRecordsByMatchNames",
        json=[[rec(5, "Homostichanthus duerdeni", match_type="phonetic")]],
    )
    ov = {
        ("Homostichantus duerdenii", "worms:5"): Override(
            "worms", "worms:5", "accept", "misspelling"
        )
    }
    m = TaxonResolver(http, ov).worms("t", "Homostichantus duerdenii", "species")
    assert m.status == "accepted"
    assert m.mapping_justification == "semapv:ManualMappingCuration"


# -------------------------------------------------------------- GBIF, NCBI
@responses.activate
def test_gbif_fuzzy_is_candidate(http):
    responses.get(
        GBIF,
        json={
            "matchType": "FUZZY",
            "usageKey": 9,
            "rank": "SPECIES",
            "phylum": "Cnidaria",
            "scientificName": "Palythoa caribbea",
            "canonicalName": "Palythoa caribbea",
            "confidence": 98,
        },
    )
    m = TaxonResolver(http).gbif("t", "Palythoa caribbeorum", "species")
    assert m.status == "candidate" and m.predicate_id is None


@responses.activate
def test_gbif_higher_rank_is_unresolved(http):
    responses.get(
        GBIF, json={"matchType": "HIGHERRANK", "usageKey": 3, "rank": "GENUS", "phylum": "Cnidaria"}
    )
    assert TaxonResolver(http).gbif("t", "Anthopleura cascaia", "species").status == "unresolved"


@responses.activate
def test_ncbi_falls_back_to_accepted_name_as_close_match(http):
    esearch, esummary = f"{NCBI}/esearch.fcgi", f"{NCBI}/esummary.fcgi"
    responses.get(
        esearch,
        json={"esearchresult": {"idlist": []}},
        match=[
            responses.matchers.query_param_matcher(
                {"db": "taxonomy", "term": "Aiptasia pallida[Scientific Name]", "retmode": "json"}
            )
        ],
    )
    responses.get(
        esearch,
        json={"esearchresult": {"idlist": ["77"]}},
        match=[
            responses.matchers.query_param_matcher(
                {
                    "db": "taxonomy",
                    "term": "Exaiptasia diaphana[Scientific Name]",
                    "retmode": "json",
                }
            )
        ],
    )
    responses.get(
        esummary,
        json={"result": {"77": {"scientificname": "Exaiptasia diaphana", "rank": "species"}}},
    )
    m = TaxonResolver(http).ncbi("t", "Aiptasia pallida", "species", "Exaiptasia diaphana")
    assert (m.predicate_id, m.match_type, m.object_id) == (
        "skos:closeMatch",
        "via_accepted_name",
        "NCBITaxon:77",
    )


@responses.activate
def test_ncbi_name_mismatch_in_summary_is_unresolved(http):
    responses.get(f"{NCBI}/esearch.fcgi", json={"esearchresult": {"idlist": ["5"]}})
    responses.get(
        f"{NCBI}/esummary.fcgi",
        json={"result": {"5": {"scientificname": "Other name", "rank": "species"}}},
    )
    assert TaxonResolver(http).ncbi("t", "A b", "species", None).status == "unresolved"


def test_normalise_authority():
    assert normalise_authority("(Duchassaing & Michelotti, 1864a)") == normalise_authority(
        "Duchassaing & Michelotti, 1864"
    )
    assert normalise_authority("(Ellis, 1768)") != normalise_authority("Le Sueur, 1818")


# ---------------------------------------------------------------- habitats
@responses.activate
def test_habitat_negation_and_label_check(http):
    responses.get(
        "https://www.ebi.ac.uk/ols4/api/search",
        json={
            "response": {
                "docs": [{"label": "intertidal zone", "obo_id": "ENVO:00000316", "iri": "x"}]
            }
        },
    )
    stmts = pd.DataFrame(
        [
            {
                "habitat_statement_id": "h1",
                "taxon_id": "t1",
                "habitat_text": "in shallow waters, but not intertidal zones.",
            }
        ]
    )
    vocab = pd.DataFrame(
        [{"phrase_regex": "intertidal zones?", "envo_label": "intertidal zone", "kind": "zone"}]
    )
    (a,) = annotate(stmts, vocab, EnvoLookup(http))
    assert a.status == "negated" and a.envo_id is None


@responses.activate
def test_habitat_label_mismatch_is_unresolved(http):
    responses.get(
        "https://www.ebi.ac.uk/ols4/api/search",
        json={
            "response": {"docs": [{"label": "coral reef", "obo_id": "ENVO:00000150", "iri": "x"}]}
        },
    )
    t = EnvoLookup(http).term("coral rubble")
    assert t.status == "unresolved" and t.envo_id is None
