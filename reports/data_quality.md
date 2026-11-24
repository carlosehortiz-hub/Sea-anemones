# Data-quality report

**Status: PASS** - 12 canonical tables, 1348 rows.

| check family | checks | failing |
|---|---:|---:|
| Column-level (Pandera, generated from LinkML) | 269 | 0 values |
| Cross-table critical rules | 14 | 0 |
| Cross-table warnings | 11 | 10 rules, 46 rows |

Critical failures stop the pipeline before RDF generation. Warnings are reported with their rows and never altered.

## Rules

| id | severity | dimension | rule | failing rows |
|---|---|---|---|---:|
| C01 | critical | consistency | occurrence.locality_id references an existing locality | 0 |
| C02 | critical | consistency | identification references an existing occurrence and taxon | 0 |
| C03 | critical | consistency | distribution references an existing taxon, locality and reference | 0 |
| C04 | critical | consistency | taxon_name_variant, habitat_statement and taxon_mapping reference an existing taxon | 0 |
| C05 | critical | consistency | a site's parent is an existing locality of level 'area' | 0 |
| C06 | critical | uniqueness | every occurrence has exactly one current identification | 0 |
| C07 | critical | uniqueness | no duplicate specimens: catalogue numbers and field codes are unique | 0 |
| C08 | critical | uniqueness | no duplicate Table 1 assertions (taxon, area, evidence, reference) | 0 |
| C09 | critical | validity | coordinates are given as a pair or not at all | 0 |
| C10 | critical | consistency | new records ('N') are only set on this-survey assertions | 0 |
| C11 | critical | consistency | a mapping asserts an identifier and predicate if and only if it is accepted | 0 |
| C12 | critical | consistency | every taxon has exactly one mapping row per service (gaps are explicit) | 0 |
| C13 | critical | consistency | WoRMS identifiers and their accepted-name pointers resolve to stored WoRMS records | 0 |
| C14 | critical | consistency | habitat annotations carry an ENVO id if and only if accepted, on an existing statement | 0 |
| W01 | warning | validity | verbatim date that is not a valid calendar date | 1 |
| W02 | warning | completeness | occurrence without locality ('-' in the source) | 2 |
| W03 | warning | completeness | specimen whose current identification has no taxon | 3 |
| W04 | warning | completeness | specimen without a MOHBR catalogue number | 1 |
| W05 | warning | completeness | collecting site not linked to a Table 1 area | 4 |
| W06 | warning | completeness | taxon with no accepted identifier in any service | 0 |
| W07 | warning | completeness | habitat statement with no ENVO annotation | 2 |
| W08 | warning | consistency | Table 1 '*' (this survey) in a sampled area, but no Table 2 specimen of that taxon there | 13 |
| W09 | warning | consistency | Table 2 specimen in an area, but no Table 1 '*' for that taxon and area | 7 |
| W10 | warning | consistency | Table 1 'a' (MOHBR) in an area, but no Table 3 specimen of that taxon there | 5 |
| W11 | warning | consistency | Table 3 specimen in an area, but no Table 1 'a' for that taxon and area | 8 |

## Failing rows

### W01 - verbatim date that is not a valid calendar date (1)

| source_ref      | locality                              | verbatim_event_date   | catalog_number   |
|:----------------|:--------------------------------------|:----------------------|:-----------------|
| Table 3, row 73 | Laguna de La Restinga, Isla Margarita | 31/04/2012            | I-1201           |

### W02 - occurrence without locality ('-' in the source) (2)

| source_ref      | locality   | verbatim_event_date   | catalog_number   |
|:----------------|:-----------|:----------------------|:-----------------|
| Table 3, row 47 | <NA>       | <NA>                  | I-939            |
| Table 3, row 48 | <NA>       | 01/03/1953            | I-942            |

### W03 - specimen whose current identification has no taxon (3)

| source_ref      | taxon   | verbatim_name   |
|:----------------|:--------|:----------------|
| Table 3, row 17 | <NA>    | not identified  |
| Table 3, row 56 | <NA>    | not identified  |
| Table 3, row 57 | <NA>    | not identified  |

### W04 - specimen without a MOHBR catalogue number (1)

| source_ref      | locality      | verbatim_event_date   | catalog_number   |
|:----------------|:--------------|:----------------------|:-----------------|
| Table 2, row 39 | Punta la Cruz | <NA>                  | <NA>             |

### W05 - collecting site not linked to a Table 1 area (4)

| source_ref      | locality                                   | verbatim_locality                          | locality_name                              |
|:----------------|:-------------------------------------------|:-------------------------------------------|:-------------------------------------------|
| Table 3, row 1  | Laguna de Punta de Piedras, Isla Margarita | Laguna de Punta de Piedras, Isla Margarita | Laguna de Punta de Piedras, Isla Margarita |
| Table 3, row 41 | Golfo de Cariaco                           | Golfo de Cariaco                           | Golfo de Cariaco                           |
| Table 3, row 59 | Ensenada Penetepe, Golfo de Cariaco        | Ensenada Penetepe, Golfo de Cariaco        | Ensenada Penetepe, Golfo de Cariaco        |
| Table 3, row 74 | Bajo Manzanillo, Isla Margarita            | Bajo Manzanillo, Isla Margarita            | Bajo Manzanillo, Isla Margarita            |

### W07 - habitat statement with no ENVO annotation (2)

| source_ref                                                | taxon                    |
|:----------------------------------------------------------|:-------------------------|
| Systematics, account of Bunodeopsis antilliensis, Habitat | Bunodeopsis antilliensis |
| Systematics, account of Calliactis tricolor, Habitat      | Calliactis tricolor      |

### W08 - Table 1 '*' (this survey) in a sampled area, but no Table 2 specimen of that taxon there (13)

| source_ref                                                                    | taxon                     | locality                                  |
|:------------------------------------------------------------------------------|:--------------------------|:------------------------------------------|
| Table 1, row 13, block A col 2, code '*' (records documented in our surveys)  | Condylactis gigantea      | Morrocoy National Park                    |
| Table 1, row 16, block A col 9, code '*' (records documented in our surveys)  | Actinoporus elegans       | Mochima National Park                     |
| Table 1, row 39, block A col 9, code '*' (records documented in our surveys)  | Palythoa caribaeorum      | Mochima National Park                     |
| Table 1, row 46, block A col 9, code '*' (records documented in our surveys)  | Zoanthus sociatus         | Mochima National Park                     |
| Table 1, row 3, block B col 4, code '*' (records documented in our surveys)   | Actinostella flosculifera | Laguna de la Restinga (Isla de Margarita) |
| Table 1, row 11, block B col 4, code '*' (records documented in our surveys)  | Bunodosoma granuliferum   | Laguna de la Restinga (Isla de Margarita) |
| Table 1, row 19, block B col 4, code '*' (records documented in our surveys)  | Stichodactyla helianthus  | Laguna de la Restinga (Isla de Margarita) |
| Table 1, row 20, block B col 10, code '*' (records documented in our surveys) | Bartholomea annulata      | Archipiélago Los Roques National Park     |
| Table 1, row 25, block B col 10, code '*' (records documented in our surveys) | Lebrunia neglecta         | Archipiélago Los Roques National Park     |
| Table 1, row 26, block B col 10, code '*' (records documented in our surveys) | Bunodeopsis antilliensis  | Archipiélago Los Roques National Park     |
| Table 1, row 39, block B col 10, code '*' (records documented in our surveys) | Palythoa caribaeorum      | Archipiélago Los Roques National Park     |
| Table 1, row 46, block B col 10, code '*' (records documented in our surveys) | Zoanthus sociatus         | Archipiélago Los Roques National Park     |
| Table 1, row 50, block B col 10, code '*' (records documented in our surveys) | Parazoanthus parasiticus  | Archipiélago Los Roques National Park     |

### W09 - Table 2 specimen in an area, but no Table 1 '*' for that taxon and area (7)

| source_ref      | taxon                    | locality        | area                                  | verbatim_event_date   | catalog_number   |
|:----------------|:-------------------------|:----------------|:--------------------------------------|:----------------------|:-----------------|
| Table 2, row 13 | Actiniidae               | Boca Seca       | Morrocoy National Park                | <NA>                  | I-1588           |
| Table 2, row 22 | Bunodeopsis antilliensis | Las Luisas      | Morrocoy National Park                | <NA>                  | I-1597           |
| Table 2, row 60 | Actiniidae               | Arena y Manglar | Archipiélago Los Roques National Park | <NA>                  | I-1634           |
| Table 2, row 71 | Condylactis gigantea     | Las Cabeceras   | Isla de Cubagua                       | <NA>                  | I-1645           |
| Table 2, row 78 | Parazoanthus parasiticus | Las Cabeceras   | Isla de Cubagua                       | <NA>                  | I-1652           |
| Table 2, row 81 | Actiniidae               | Las Cabeceras   | Isla de Cubagua                       | <NA>                  | I-1655           |
| Table 2, row 87 | Bunodeopsis antilliensis | Las Cabeceras   | Isla de Cubagua                       | <NA>                  | I-1661           |

### W10 - Table 1 'a' (MOHBR) in an area, but no Table 3 specimen of that taxon there (5)

| source_ref                                                                                               | taxon                    | locality                    |
|:---------------------------------------------------------------------------------------------------------|:-------------------------|:----------------------------|
| Table 1, row 17, block A col 6, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Homostichanthus duerdeni | Playa Azul, litoral Central |
| Table 1, row 19, block A col 2, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Stichodactyla helianthus | Morrocoy National Park      |
| Table 1, row 26, block A col 2, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Bunodeopsis antilliensis | Morrocoy National Park      |
| Table 1, row 42, block A col 2, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Palythoa variabilis      | Morrocoy National Park      |
| Table 1, row 27, block B col 9, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Diadumene lineata        | Golfo de Paria              |

### W11 - Table 3 specimen in an area, but no Table 1 'a' for that taxon and area (8)

| source_ref      | taxon                | locality                                      | area                        | verbatim_event_date   | catalog_number   |
|:----------------|:---------------------|:----------------------------------------------|:----------------------------|:----------------------|:-----------------|
| Table 3, row 14 | Zoanthus sociatus    | Cayo Sombrero, Morrocoy                       | Morrocoy National Park      | 09/08/1984            | I-893            |
| Table 3, row 26 | Actinoporus elegans  | Playa Azul, Municipio Vargas, Litoral Central | Playa Azul, litoral Central | 13/03/1985            | I-907            |
| Table 3, row 30 | Condylactis gigantea | Isla de Pájaros                               | Isla de Pájaros, Maracaibo  | 12/03/1985            | I-912            |
| Table 3, row 35 | Zoanthus pulchellus  | Isla de Aves                                  | Isla de Aves                | 01/10/1988            | I-917            |
| Table 3, row 54 | Palythoa caribaeorum | Isla La Blanquilla                            | Isla La Blanquilla          | 01/08/1987            | I-950            |
| Table 3, row 55 | Palythoa caribaeorum | Playa Azul, Morrocoy                          | Morrocoy National Park      | 14/05/1985            | I-953            |
| Table 3, row 58 | Palythoa caribaeorum | Isla La Tortuga                               | Isla Tortuga                | 01/05/1986            | I-956            |
| Table 3, row 60 | Zoanthus sociatus    | Isla La Blanquilla                            | Isla La Blanquilla          | 01/08/1987            | I-961            |

## Completeness (columns below 100 %)

Optional fields: a gap here is information about the source, not an error.

| table              | column                     |   rows |   non_null |   pct |
|:-------------------|:---------------------------|-------:|-----------:|------:|
| distribution       | occurrence_remarks         |    342 |          2 |   0.6 |
| distribution       | reference_code             |    342 |        285 |  83.3 |
| distribution       | locality_id                |    342 |        340 |  99.4 |
| habitat_annotation | comment                    |     65 |         16 |  24.6 |
| habitat_annotation | envo_id                    |     65 |         49 |  75.4 |
| identification     | identification_qualifier   |    237 |          9 |   3.8 |
| identification     | identification_remarks     |    237 |         28 |  11.8 |
| identification     | taxon_id                   |    237 |        233 |  98.3 |
| locality           | decimal_latitude           |     71 |         17 |  23.9 |
| locality           | decimal_longitude          |     71 |         17 |  23.9 |
| locality           | verbatim_coordinates       |     71 |         17 |  23.9 |
| locality           | region                     |     71 |         26 |  36.6 |
| locality           | sampled_in_study           |     71 |         26 |  36.6 |
| locality           | parent_locality_id         |     71 |         41 |  57.7 |
| locality           | state_province             |     71 |         44 |  62   |
| occurrence         | occurrence_remarks         |    212 |          2 |   0.9 |
| occurrence         | recorded_by                |    212 |         58 |  27.4 |
| occurrence         | verbatim_event_date        |    212 |         81 |  38.2 |
| occurrence         | other_catalog_numbers      |    212 |        128 |  60.4 |
| occurrence         | event_date                 |    212 |        139 |  65.6 |
| occurrence         | locality_id                |    212 |        210 |  99.1 |
| occurrence         | catalog_number             |    212 |        211 |  99.5 |
| taxon              | scientific_name_authorship |     61 |         26 |  42.6 |
| taxon              | family_authorship          |     61 |         44 |  72.1 |
| taxon              | table1_row                 |     61 |         52 |  85.2 |
| taxon              | family                     |     61 |         53 |  86.9 |
| taxon              | order                      |     61 |         53 |  86.9 |
| taxon              | specific_epithet           |     61 |         59 |  96.7 |
| taxon              | genus                      |     61 |         60 |  98.4 |
| taxon_mapping      | predicate_id               |    183 |        164 |  89.6 |
| taxon_mapping      | object_id                  |    183 |        164 |  89.6 |
| taxon_mapping      | object_label               |    183 |        165 |  90.2 |
| taxon_mapping      | confidence                 |    183 |        165 |  90.2 |
| taxon_name_variant | identification_qualifier   |     73 |          3 |   4.1 |
| worms_record       | unaccept_reason            |     67 |          5 |   7.5 |
