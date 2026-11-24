import csv
import hashlib

from anemone_kg.config import load_config


def test_config_paths_resolve():
    cfg = load_config()
    assert cfg.pdf.exists()
    assert cfg.source["doi"].startswith("10.")


def test_raw_pdf_matches_manifest():
    """data/raw is immutable: the PDF must match the checksum recorded in MANIFEST.csv."""
    cfg = load_config()
    with (cfg.path("raw") / "MANIFEST.csv").open(encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    assert hashlib.sha256(cfg.pdf.read_bytes()).hexdigest() == row["sha256"]
