"""End to end: the whole CLI, offline, into a scratch directory.

Runs `python -m anemone_kg run all` against a copy of the configuration whose
outputs go to a temporary directory, then requires every output to be
byte-identical to the committed file. This is the reproducibility claim of the
project, tested: same inputs + cached API responses -> same tables, graph,
reports and query results.
"""

from __future__ import annotations

import filecmp
import shutil

import pytest
import yaml

from anemone_kg.cli import main
from anemone_kg.config import load_config

pytestmark = pytest.mark.e2e

# Inputs read from the repository; outputs written to the scratch root.
READ_ONLY = ("model", "ontology", "shapes", "schema", "mappings")
OUTPUT_DIRS = ("data/interim", "data/processed", "reports", "queries/results")


@pytest.fixture(scope="module")
def run_root(tmp_path_factory, monkeypatch_module):
    repo = load_config().root
    root = tmp_path_factory.mktemp("e2e")
    for d in READ_ONLY:
        (root / d).symlink_to(repo / d, target_is_directory=True)
    shutil.copytree(repo / "queries", root / "queries", ignore=shutil.ignore_patterns("results"))
    cfg = yaml.safe_load((repo / "config.yaml").read_text(encoding="utf-8"))
    cfg["paths"]["raw"] = str(repo / "data" / "raw")
    cfg["paths"]["cache"] = str(repo / "data" / "cache")
    cfg["source"]["pdf"] = str(repo / cfg["source"]["pdf"])
    (root / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    (root / "data" / "cache").mkdir(parents=True)  # data/cache/vocab is read via root
    (root / "data" / "cache" / "vocab").symlink_to(
        repo / "data" / "cache" / "vocab", target_is_directory=True
    )
    monkeypatch_module.setenv("ANEMONE_KG_OFFLINE", "1")
    assert main(["--config", str(root / "config.yaml"), "run", "all"]) == 0
    return repo, root


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _files(base):
    return sorted(p.relative_to(base) for p in base.rglob("*") if p.is_file())


@pytest.mark.parametrize("out_dir", OUTPUT_DIRS)
def test_full_pipeline_reproduces_committed_outputs(run_root, out_dir):
    repo, root = run_root
    committed, produced = repo / out_dir, root / out_dir
    assert _files(produced) == _files(committed), "different set of output files"
    different = [
        str(f)
        for f in _files(committed)
        if not filecmp.cmp(committed / f, produced / f, shallow=False)
    ]
    assert different == [], f"outputs differ from the committed files: {different}"
