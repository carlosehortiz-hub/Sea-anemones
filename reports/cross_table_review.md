# Cross-table review: why each W08-W11 warning fires

33 rows flagged by the four cross-source rules. Each is given one cause (the first that applies, in the order below). Printed values were confirmed by the extraction census (reports/extraction_audit.md), so no row is an extraction artefact; 0 rows show the paired signature of a column shift.

| cause | meaning |
|---|---|
| nomenclatural | same taxon under another name (WoRMS accepted name agrees) |
| above_species | a specimen of the same family is identified only above species level |
| reidentified | re-identified in Table 3; Table 1 keeps the previous identification |
| unconfirmed | Table 3 could not confirm the identification ('not identified') |
| link | depends on an uncertain site-to-area link |
| other_code | Table 1 lists the taxon in this area, but under another code |
| as_printed | the tables differ as printed (no other cause applies) |

## Rows by rule and cause

| rule   |   above_species |   as_printed |   other_code |   reidentified |   unconfirmed |
|:-------|----------------:|-------------:|-------------:|---------------:|--------------:|
| W08    |               1 |           12 |            0 |              0 |             0 |
| W09    |               3 |            2 |            2 |              0 |             0 |
| W10    |               0 |            2 |            0 |              1 |             2 |
| W11    |               0 |            3 |            4 |              1 |             0 |

## Link sensitivity

The rules re-run with all 22 curated site-to-area links that are not an exact name or a printed park name set to unlinked, as curated, and all linked (the three links the curator rejected included).

| scenario     |   W08 |   W09 |   W10 |   W11 |
|:-------------|------:|------:|------:|------:|
| all_unlinked |    13 |     7 |     0 |     3 |
| as_curated   |    13 |     7 |     5 |     8 |
| all_linked   |    13 |     7 |     6 |     9 |

## Every flagged row

| rule   | source_ref                                                                                               | taxon                     | area                                      | table1_column   | cause         | evidence                                                         | rests_on_curated_link   | shift_pair   |
|:-------|:---------------------------------------------------------------------------------------------------------|:--------------------------|:------------------------------------------|:----------------|:--------------|:-----------------------------------------------------------------|:------------------------|:-------------|
| W08    | Table 1, row 13, block A col 2, code '*' (records documented in our surveys)                             | Condylactis gigantea      | Morrocoy National Park                    | T1A02           | above_species | Table 2, row 13: Actiniidae                                      | False                   | False        |
| W08    | Table 1, row 16, block A col 9, code '*' (records documented in our surveys)                             | Actinoporus elegans       | Mochima National Park                     | T1A09           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 39, block A col 9, code '*' (records documented in our surveys)                             | Palythoa caribaeorum      | Mochima National Park                     | T1A09           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 46, block A col 9, code '*' (records documented in our surveys)                             | Zoanthus sociatus         | Mochima National Park                     | T1A09           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 3, block B col 4, code '*' (records documented in our surveys)                              | Actinostella flosculifera | Laguna de la Restinga (Isla de Margarita) | T1B04           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 11, block B col 4, code '*' (records documented in our surveys)                             | Bunodosoma granuliferum   | Laguna de la Restinga (Isla de Margarita) | T1B04           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 19, block B col 4, code '*' (records documented in our surveys)                             | Stichodactyla helianthus  | Laguna de la Restinga (Isla de Margarita) | T1B04           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 20, block B col 10, code '*' (records documented in our surveys)                            | Bartholomea annulata      | Archipiélago Los Roques National Park     | T1B10           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 25, block B col 10, code '*' (records documented in our surveys)                            | Lebrunia neglecta         | Archipiélago Los Roques National Park     | T1B10           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 26, block B col 10, code '*' (records documented in our surveys)                            | Bunodeopsis antilliensis  | Archipiélago Los Roques National Park     | T1B10           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 39, block B col 10, code '*' (records documented in our surveys)                            | Palythoa caribaeorum      | Archipiélago Los Roques National Park     | T1B10           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 46, block B col 10, code '*' (records documented in our surveys)                            | Zoanthus sociatus         | Archipiélago Los Roques National Park     | T1B10           | as_printed    |                                                                  | False                   | False        |
| W08    | Table 1, row 50, block B col 10, code '*' (records documented in our surveys)                            | Parazoanthus parasiticus  | Archipiélago Los Roques National Park     | T1B10           | as_printed    |                                                                  | False                   | False        |
| W09    | Table 2, row 13                                                                                          | Actiniidae                | Morrocoy National Park                    | T1A02           | above_species | Actiniidae                                                       | False                   | False        |
| W09    | Table 2, row 22                                                                                          | Bunodeopsis antilliensis  | Morrocoy National Park                    | T1A02           | other_code    | Table 1 code(s): a, e                                            | False                   | False        |
| W09    | Table 2, row 60                                                                                          | Actiniidae                | Archipiélago Los Roques National Park     | T1B10           | above_species | Actiniidae                                                       | False                   | False        |
| W09    | Table 2, row 71                                                                                          | Condylactis gigantea      | Isla de Cubagua                           | T1B05           | as_printed    |                                                                  | False                   | False        |
| W09    | Table 2, row 78                                                                                          | Parazoanthus parasiticus  | Isla de Cubagua                           | T1B05           | other_code    | Table 1 code(s): e                                               | False                   | False        |
| W09    | Table 2, row 81                                                                                          | Actiniidae                | Isla de Cubagua                           | T1B05           | above_species | Actiniidae                                                       | False                   | False        |
| W09    | Table 2, row 87                                                                                          | Bunodeopsis antilliensis  | Isla de Cubagua                           | T1B05           | as_printed    |                                                                  | False                   | False        |
| W10    | Table 1, row 17, block A col 6, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Homostichanthus duerdeni  | Playa Azul, litoral Central               | T1A06           | reidentified  | Table 3, row 26: Homostichantus duerdenii -> Actinoporus elegans | True                    | False        |
| W10    | Table 1, row 19, block A col 2, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Stichodactyla helianthus  | Morrocoy National Park                    | T1A02           | as_printed    |                                                                  | True                    | False        |
| W10    | Table 1, row 26, block A col 2, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Bunodeopsis antilliensis  | Morrocoy National Park                    | T1A02           | as_printed    |                                                                  | True                    | False        |
| W10    | Table 1, row 42, block A col 2, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Palythoa variabilis       | Morrocoy National Park                    | T1A02           | unconfirmed   | Table 3, row 56: Palythoa variabilis -> not identified           | True                    | False        |
| W10    | Table 1, row 27, block B col 9, code 'a' (Specimens of the MOHBR scientific collection (see Appendix 2)) | Diadumene lineata         | Golfo de Paria                            | T1B09           | unconfirmed   | Table 3, row 17: Haliplanella luciae -> not identified           | True                    | False        |
| W11    | Table 3, row 14                                                                                          | Zoanthus sociatus         | Morrocoy National Park                    | T1A02           | other_code    | Table 1 code(s): *, e, f                                         | True                    | False        |
| W11    | Table 3, row 26                                                                                          | Actinoporus elegans       | Playa Azul, litoral Central               | T1A06           | reidentified  | Table 1 code under previous name Homostichantus duerdenii        | True                    | False        |
| W11    | Table 3, row 30                                                                                          | Condylactis gigantea      | Isla de Pájaros, Maracaibo                | T1A01           | other_code    | Table 1 code(s): e                                               | True                    | False        |
| W11    | Table 3, row 35                                                                                          | Zoanthus pulchellus       | Isla de Aves                              | T1B14           | as_printed    |                                                                  | False                   | False        |
| W11    | Table 3, row 54                                                                                          | Palythoa caribaeorum      | Isla La Blanquilla                        | T1B12           | as_printed    |                                                                  | False                   | False        |
| W11    | Table 3, row 55                                                                                          | Palythoa caribaeorum      | Morrocoy National Park                    | T1A02           | other_code    | Table 1 code(s): *, e, f                                         | True                    | False        |
| W11    | Table 3, row 58                                                                                          | Palythoa caribaeorum      | Isla Tortuga                              | T1B02           | other_code    | Table 1 code(s): e                                               | True                    | False        |
| W11    | Table 3, row 60                                                                                          | Zoanthus sociatus         | Isla La Blanquilla                        | T1B12           | as_printed    |                                                                  | False                   | False        |

## Support of Table 1 cells (taxon x area), by region

Unit: occupied cell, not code. First-hand = a survey (*) or museum (a) code.

| region          |   first-hand and literature |   first-hand only |   literature only: Agudo (1987) alone |   literature only: other or several sources |   all |
|:----------------|----------------------------:|------------------:|--------------------------------------:|--------------------------------------------:|------:|
| Central Coast   |                           4 |                 8 |                                    34 |                                           1 |    47 |
| East Coast      |                          23 |                23 |                                    90 |                                           2 |   138 |
| Oceanic Islands |                          10 |                12 |                                    12 |                                           0 |    34 |
| West Coast      |                          14 |                 2 |                                    20 |                                           6 |    42 |
| all             |                          51 |                45 |                                   156 |                                           9 |   261 |
