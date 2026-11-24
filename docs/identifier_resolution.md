# Identifier resolution and vocabulary alignment

## Taxa → WoRMS, GBIF, NCBI Taxonomy

Every taxon (a *name as used in the paper*) is looked up in three services and gets
**one row per service, resolved or not** (`taxon_mapping.csv`, exported as SSSOM in
`data/processed/mappings/taxon_mappings.sssom.tsv`).

| Step | Rule |
|---|---|
| WoRMS exact | `AphiaRecordsByName` (no wildcard). Keep records in phylum Cnidaria at the same rank. |
| Homonyms | Several records left → keep the one whose authority equals the authority printed in the paper (parentheses and year letter ignored). Otherwise `ambiguous`. |
| WoRMS fuzzy | `AphiaRecordsByMatchNames` only if the exact lookup is empty. Result is a `candidate`. |
| Synonyms | If the matched record is not accepted, the accepted record (`valid_AphiaID`) is fetched and stored too, so both names are graph nodes. |
| GBIF | `species/match` with phylum and rank. `EXACT` with the same canonical name → accepted. `FUZZY` → candidate. Anything else → unresolved. |
| NCBI | `esearch` on `[Scientific Name]` and then `esummary` to check that name and rank are identical. If the paper name is absent, the WoRMS accepted name is tried and recorded as `skos:closeMatch` (`via_accepted_name`). |

**Statuses.** `accepted` is the only status that asserts a mapping (`predicate_id` set).
`candidate`, `ambiguous` and `unresolved` rows carry no identifier into the graph. A
curator can accept or reject a candidate in `mappings/resolution_overrides.csv`. An
accepted candidate is labelled `semapv:ManualMappingCuration`, not lexical matching.

**Confidence.** It is 1.0 for exact matches. For GBIF it is GBIF's own score. For WoRMS
fuzzy match types it is a fixed scale (phonetic 0.8, near_1 0.7, near_2 0.5, near_3 0.3)
that **has no external source**. It only orders candidates for review.

## Habitats → ENVO

1. A curated vocabulary (`mappings/habitat_vocabulary.csv`) maps phrases in the species
   accounts to ENVO **labels**. This is a human decision.
2. The label is resolved to an IRI through EBI OLS by **exact label**. IRIs are never
   typed by hand, and a label with no exact hit stays `unresolved` (e.g. *coral rubble*).
3. A match preceded by a negation ("but not intertidal zones") is recorded as `negated`
   and not annotated.

## Reproducibility

Every response is cached in `data/cache/<service>/` and committed. Each mapping row
names its cache file (`cache_key`) and retrieval time (`mapping_date`).
`ANEMONE_KG_OFFLINE=1` (as set in CI) never touches the network. A cache miss becomes
`unresolved`, never a guess.
