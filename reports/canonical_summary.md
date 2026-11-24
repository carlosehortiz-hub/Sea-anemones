# Canonicalisation summary

## Tables

| table | rows |
|---|---:|
| `source_document` | 1 |
| `reference` | 10 |
| `taxon` | 61 |
| `taxon_name_variant` | 73 |
| `locality` | 71 |
| `occurrence` | 212 |
| `identification` | 237 |
| `distribution` | 342 |
| `habitat_statement` | 26 |

## Record flow (nothing is dropped silently)

| flow | in | out | merged | dropped | note |
|---|---:|---:|---:|---:|---|
| Table 2 specimens -> occurrence | 128 | 128 | 0 | 0 | one occurrence per specimen |
| Table 3 specimens -> occurrence | 84 | 84 | 0 | 0 | one occurrence per specimen |
| Table 1 codes -> distribution | 344 | 342 | 2 | 0 | 'N' codes folded into is_new_record of the '*' row (R_NEW_RECORD_FOLD) |
| Species accounts -> habitat_statement | 26 | 26 | 0 | 0 | one statement per account |
| Specimens -> current identification | 212 | 212 | 0 | 0 | one current identification per specimen |

## Rules applied

| rule | count | definition |
|---|---:|---|
| `R_ACCOUNT_JOIN` | 26 | Authorship from the species account whose heading has the same name. |
| `R_CATALOG` | 1 | MOHBR catalogue number; non-identifier text ('In progress') -> null + remark. |
| `R_CODE_KIND` | 342 | Table 1 code -> evidence kind and cited reference (legend). |
| `R_CROSSWALK` | 45 | Site -> Table 1 area via mappings/locality_crosswalk.csv (accepted rows only). |
| `R_DATE_DMY` | 85 | dd/mm/yyyy -> ISO 8601; impossible calendar dates -> null, verbatim kept. |
| `R_DATE_METHODS` | 128 | Event date stated in Methods per park, from mappings/event_dates.csv. |
| `R_DMS` | 256 | Degrees-minutes-seconds -> decimal degrees, 6 dp; W and S negative. |
| `R_FLAGS` | 52 | Table 1 marks after a name: dagger -> flag_invalid, '?' -> flag_doubtful. |
| `R_HIGHER_FROM_T1` | 1 | Order of a family-rank name, from the Table 1 order listing that family. |
| `R_INFORMAL` | 1 | Informal label (e.g. 'Actinia 1') -> no taxon; kept verbatim with a remark. |
| `R_MISSING` | 2 | '-' or empty string -> null (the paper's placeholder for 'not recorded'). |
| `R_NEW_RECORD_FOLD` | 2 | Code 'N' sets is_new_record on the '*' record of the same cell. |
| `R_NOT_IDENTIFIED` | 3 | 'not identified' -> no taxon; kept verbatim with a remark. |
| `R_OPEN_SEA` | 3 | Table 1 'Open Sea Distribution' column -> no locality, kept as remark. |
| `R_PERSON` | 2 | Collectors: fix 'Agudo. I.' -> 'Agudo, I.'; ' and ' -> ' | ' (DwC list). |
| `R_PREVIOUS_ID` | 25 | Table 3 previous identification kept only when it differs from current. |
| `R_RANK_FROM_NAME` | 61 | Rank from name form: binomial=species, '-idae'=family, else genus. |
| `R_RANK_HEADING` | 104 | 'Family ACTINIIDAE Rafinesque, 1815' -> 'Actiniidae' + authorship. |
| `R_SPLIT_QUALIFIER` | 11 | Split an open-nomenclature qualifier (cf., sp., sp.?) off the name. |
| `R_STATE` | 5 | State spelling from mappings/state_names.csv. |
| `R_TYPO` | 4 | Curated spelling correction from mappings/name_variants.csv (status accepted). |

## Individual changes and gaps

| rule | source | detail |
|---|---|---|
| `R_OPEN_SEA` | Table 1, header, block B col 15 | column not modelled as a locality |
| `R_STATE` | Table 2, row 1 | 'Falcon' -> 'Falcón' |
| `R_STATE` | Table 2, row 5 | 'Falcon' -> 'Falcón' |
| `R_STATE` | Table 2, row 6 | 'Falcon' -> 'Falcón' |
| `R_STATE` | Table 2, row 8 | 'Falcon' -> 'Falcón' |
| `R_STATE` | Table 2, row 21 | 'Falcon' -> 'Falcón' |
| `R_TYPO` | Table 2, row 25 | 'Phymantus crucifer' -> 'Phymanthus crucifer' |
| `R_CATALOG` | Table 2, row 39 | MOHBR catalogue number given as 'In progress' in the source |
| `R_TYPO` | Table 2, row 87 | 'Bunodeopsis antillensis' -> 'Bunodeopsis antilliensis' |
| `R_TYPO` | Table 2, row 122 | 'Anemonia sargassansis' -> 'Anemonia sargassensis' |
| `R_TYPO` | Table 2, row 123 | 'Callactis tricolor' -> 'Calliactis tricolor' |
| `R_CROSSWALK` | Table 3, row 1 | no accepted area for 'Laguna de Punta de Piedras, Isla Margarita' (table3) |
| `R_INFORMAL` | Table 3, row 1 | 'Actinia 1' is not a scientific name |
| `R_NOT_IDENTIFIED` | Table 3, row 17 | previous: 'Haliplanella luciae' |
| `R_CROSSWALK` | Table 3, row 41 | no accepted area for 'Golfo de Cariaco' (table3) |
| `R_MISSING` | Table 3, row 47 | locality not recorded ('-') |
| `R_MISSING` | Table 3, row 48 | locality not recorded ('-') |
| `R_PERSON` | Table 3, row 50 | 'Gil. R.' -> 'Gil, R.' |
| `R_PERSON` | Table 3, row 56 | 'Agudo. I.' -> 'Agudo, I.' |
| `R_NOT_IDENTIFIED` | Table 3, row 56 | previous: 'Palythoa variabilis' |
| `R_NOT_IDENTIFIED` | Table 3, row 57 | previous: 'Isaurus duchassaingi' |
| `R_CROSSWALK` | Table 3, row 59 | no accepted area for 'Ensenada Penetepe, Golfo de Cariaco' (table3) |
| `R_DATE_DMY` | Table 3, row 73 | '31/04/2012': impossible calendar date |

## Awaiting review (not applied)

- crosswalk: `Laguna de Punta de Piedras, Isla Margarita` -> `T1B03`? Is 'Laguna de Punta de Piedras' the Table 1 'Laguna de Piedras'? Not stated in the paper
- crosswalk: `Golfo de Cariaco` -> `T1A12`? Table 1 column is 'La Chica' within the gulf; the gulf is broader
- crosswalk: `Ensenada Penetepe, Golfo de Cariaco` -> `T1A12`? Same question as above

## Taxa by role

- `table1`: 52
- `table2`: 25
- `table3_current`: 19
- `table3_previous`: 12
- `species_account`: 26
- names used only as superseded identifications (8): Aiptasia pallida, Telmatactis rufa, Lebrunia danae, Haliplanella luciae, Homostichantus duerdenii, Palythoa caribbeorum, Bunodosoma cavernata, Phyllactis praetexta
