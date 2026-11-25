# Identifier resolution report

## Taxa: status per service

| service | accepted | candidate | ambiguous | unresolved |
|---|---:|---:|---:|---:|
| worms | 61 | 0 | 0 | 0 |
| gbif | 59 | 0 | 0 | 2 |
| ncbi | 44 | 0 | 0 | 17 |

## Match types (accepted rows)

- worms: exact_accepted 45, exact_synonym 13, fuzzy 3
- gbif: exact_accepted 46, exact_synonym 10, fuzzy 3
- ncbi: exact_accepted 34, via_accepted_name 10

## Names whose WoRMS accepted name differs from the paper (13)

| name in paper | WoRMS record (status) | accepted name |
|---|---|---|
| Anthopleura cascaia | worms:283343 (nomen nudum) | Anthopleura correae (worms:1873438) |
| Exaiptasia pallida | worms:888637 (alternative representation) | Exaiptasia diaphana (worms:1264073) |
| Corynactis caribbeorum | worms:592855 (unaccepted) | Pseudocorynactis caribbeorum (worms:101017) |
| Isaurus duchassaingi | worms:101056 (unaccepted) | Isaurus tuberculatus (worms:101058) |
| Zoanthus proteus | worms:590578 (unaccepted) | Zoanthus sociatus (worms:288843) |
| Epizoanthus cutressi | worms:581448 (unaccepted) | Bergia cutressi (worms:853594) |
| Parazoanthus catenularis | worms:283867 (unaccepted) | Bergia catenularis (worms:853592) |
| Parazoanthus parasiticus | worms:283871 (unaccepted) | Umimayanthus parasiticus (worms:847839) |
| Parazoanthus puertoricense | worms:488982 (unaccepted) | Bergia puertoricense (worms:853593) |
| Aiptasia pallida | worms:283486 (unaccepted) | Exaiptasia diaphana (worms:1264073) |
| Lebrunia danae | worms:290278 (unaccepted) | Lebrunia neglecta (worms:742298) |
| Haliplanella luciae | worms:100873 (unaccepted) | Diadumene lineata (worms:395099) |
| Bunodosoma cavernata | worms:283411 (unaccepted) | Bunodosoma cavernatum (worms:592952) |

## Needs attention (19 rows) - nothing here was guessed

| name | service | status | candidate | confidence | comment |
|---|---|---|---|---:|---|
| Actinoporus elegans | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Anemonia sargassensis | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Anthopleura cascaia | gbif | unresolved |  |  | GBIF matchType HIGHERRANK, rank GENUS |
| Bartholomea werneri | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Bunodeopsis antilliensis | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Bunodosoma kuekenthali | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Ceriantheopsis americanus | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Corynactis caribbeorum | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Homostichantus duerdenii | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Isoaulactinia stelloides | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Monactis vestita | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Pachycerianthus curacaoensis | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Palythoa caribbeorum | gbif | unresolved |  | 0.98 | rejected by curator: GBIF fuzzy match is Palythoa caribbea, a different species. |
| Palythoa caribbeorum | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Palythoa mammillosa | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Phyllactis praetexta | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Scolanthus curacaoensis | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Telmatactis rufa | ncbi | unresolved |  |  | not in NCBI Taxonomy |
| Telmatactis vernonia | ncbi | unresolved |  |  | not in NCBI Taxonomy |

## Habitats -> ENVO

- 65 phrase matches: accepted 49, unresolved 14, negated 2
- 24 of 26 habitat statements have at least one ENVO term

| ENVO term | id | kind | statements |
|---|---|---|---:|
| cave | ENVO:00000067 | habitat | 1 |
| coral reef | ENVO:00000150 | habitat | 1 |
| crevice | ENVO:01000294 | habitat | 5 |
| mangrove swamp | ENVO:00000057 | habitat | 2 |
| marine coral reef back reef | ENVO:01000145 | zone | 2 |
| marine coral reef crest | ENVO:01000146 | zone | 1 |
| marine coral reef fore reef | ENVO:01000147 | zone | 2 |
| mud | ENVO:01000001 | substrate | 1 |
| rock | ENVO:00001995 | substrate | 19 |
| sand | ENVO:01000017 | substrate | 6 |
| sea grass bed | ENVO:01000059 | habitat | 4 |

Negated (not annotated): 'intertidal zones' (preceded by negation: 'not'); 'intertidal zones' (preceded by negation: 'not on')
Unresolved labels (no ENVO class): coral rubble

## Cache

- responses served from cache: 417, fetched: 0
