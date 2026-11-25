# Extraction census: a second automated extraction and a rendered-image check

**Status: AGREE.** Every cell of Table 1 and every field of Tables 2 and 3 was extracted a second time, with another PDF engine and parser, and every Table 1 cell was checked for ink on the rendered page.

First extraction: pdfplumber (pdfminer.six) (the pipeline). Second extraction: Poppler pdftotext -bbox with a separate parser (`anemone_kg.audit.second_reading`). Both read the PDF's text layer, so they agree on anything wrong in that layer; the rendered-image check does not read it.

| table | unit | extraction | second extraction | agree |
|---|---|---:|---:|---:|
| Table 1 | occupied cells | 263 | 263 | 263 |
| Table 1 | evidence codes | 344 | 344 | 344 |
| Table 2 | rows | 128 | 128 | - |
| Table 2 | fields (0 blank) | 1024 | - | 1024 |
| Table 3 | rows | 84 | 84 | - |
| Table 3 | fields (1 blank) | 588 | - | 588 |

A Table 1 code agrees when both extractions put it in the same row and column. A field of Tables 2 and 3 agrees when the text printed inside that column's band of the same row equals the extracted value (whitespace ignored), blanks included.

The two extractions share this layout knowledge: the page ranges of Tables 1-3; rows are anchored on the row numbers printed in the left margin; Table 1 has two column blocks; columns are numbered left to right within a block; the legend's code set (a-j, *, N); the printed column order of Tables 2 and 3 (from their header words). They share no code, PDF engine, word segmentation, column building or row grouping.

The census found no disagreement at its first run; no parser was changed to reach agreement.

## Rendered-image check of Table 1

Pages rasterised with Poppler pdftoppm at 150 dpi (glyphs and vector paths). Each cell rectangle (row band x column band) is tested for ink; no glyph inside a cell is read. The rectangles come from text-layer positions (printed row numbers and column headers) shared with the second extraction. The check sees a code missing from an empty cell, not one missing from a cell that holds another code, and not the identity of a code.

| cells | with a code and ink | empty and no ink | ink without a code | code without ink |
|---:|---:|---:|---:|---:|
| 1404 | 263 | 1141 | 0 | 0 |

Every occupied cell has more ink than any empty cell: yes.

Engine versions and the ink margin (faintest occupied cell, darkest empty cell) are written to the run log, not to this report, so that the committed report does not depend on the Poppler build.

## Table 3 against the article's own prose

The Results list 19 species with their number of MOHBR specimens (81 specimens); the extracted current identifications of Table 3 give 81. 19 of 19 species agree. The same sentence states 22 species while listing 19.

## Disagreements

None.
