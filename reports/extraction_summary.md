# Extraction summary

| file | rows | content |
|---|---:|---|
| `table1_taxa.csv` | 52 | 52 taxon rows of Table 1 |
| `table1_localities.csv` | 27 | 27 locality columns of Table 1 |
| `table1_cells.csv` | 344 | one row per code in a Table 1 cell (taxon x locality x code) |
| `table1_legend.csv` | 14 | codes and their meaning, from the Table 1 legend |
| `table2_specimens.csv` | 128 | 128 specimens collected in the study (Appendix 1) |
| `table3_mohbr_specimens.csv` | 84 | 84 MOHBR collection specimens examined (Appendix 2) |
| `species_accounts.csv` | 26 | 26 species accounts: heading, authority, habitat paragraph |

## Table 1

- 52 taxon rows, 27 locality columns (6 in bold = sampled in this study: Morrocoy National Park, Chichiriviche de la Costa, Mochima National Park, Laguna de la Restinga (Isla de Margarita), Isla de Cubagua, Archipiélago Los Roques National Park).
- 344 codes in 263 non-empty cells. Codes per kind:
  - `*` records documented in our surveys: **57**
  - `N` new records for Venezuela: **2**
  - `a` Specimens of the MOHBR scientific collection (see Appendix 2): **56**
  - `b` den Hartog (1980): **1**
  - `c` Knowlton & Keller (1985): **2**
  - `d` Riemann-Zürneck (1986): **1**
  - `e` Agudo (1987): **207**
  - `f` Bastidas & Bone (1996): **7**
  - `g` Bitter-Soto (1999): **2**
  - `h` Henríquez & Palacios (2008): **1**
  - `i` Liñero-Arana & González (2008): **1**
  - `j` Carrasquel (2012): **7**
- Taxon rows with no code in any cell (0): 
- Flags: † (invalid) on Anthopleura cascaia †, Bartholomea werneri †, Zoanthus proteus †; ? (doubtful) on Bunodosoma caissarum ?, Bunodosoma cangicum ?, Bunodosoma kuekenthali ?, Phymactis sp.?, Palythoa mammillosa ?.
- New records (N): Anthopleura pallida @ Morrocoy National Park; Telmatactis vernonia @ Mochima National Park

## Tables 2 and 3

- Table 2: 128 specimens, 29 distinct names, 16 localities in 5 parks/areas.
- Table 3: 84 specimens, 26 previous and 20 current identifications; 25 specimens were re-identified.

## Names that differ between sources (to resolve in steps 2-3)

- Table 2 species not in Table 1 (6): Actiniidae sp., Anemonia sargassansis, Bunodeopsis antillensis, Callactis tricolor, Phymantus crucifer, Zoanthus cf. pulchellus
- Table 3 current identification not in Table 1 (1): not identified
- Species account headings not in Table 1 (1): Zoanthus cf. pulchellus
- Orders in Table 1: ['ACTINIARIA', 'CERIANTHARIA', 'CORALLIMORPHARIA', 'ZOANTHIDEA']; in species accounts: ['ACTINIARIA', 'CERIANTHARIA', 'CORALLIMORPHARIA', 'ZOANTHARIA']
