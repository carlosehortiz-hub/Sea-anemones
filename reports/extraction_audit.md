# Extraction census: second, independent transcription

**Status: AGREE** - every occupied cell of Table 1 and every field of Tables 2 and 3 was read a second time, with a different PDF engine and parser, and compared with the extraction.

First reading: pdfplumber (pdfminer.six) (the pipeline's extraction). Second reading: Poppler pdftotext -bbox with a separate parser (`anemone_kg.audit.second_reading`).

| table | unit | extraction | second reading | agree |
|---|---|---:|---:|---:|
| Table 1 | occupied cells | 263 | 263 | 263 |
| Table 1 | evidence codes | 344 | 344 | 344 |
| Table 2 | rows | 128 | 128 | - |
| Table 2 | non-empty fields | 1024 | - | 1024 |
| Table 3 | rows | 84 | 84 | - |
| Table 3 | non-empty fields | 587 | - | 587 |

A Table 1 code agrees when both readings put it in the same row and column. A field of Tables 2 and 3 agrees when all its tokens are found in the same printed row and the fields appear left to right in column order. The check detects a column shift, a value read into the wrong row, two columns swapped and a changed digit (tests/test_second_reading.py injects each of these).

## Disagreements

None.
