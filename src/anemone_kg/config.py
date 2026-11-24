"""Configuration loading.

All paths in ``config.yaml`` are relative to the repository root, so the pipeline
runs identically from a clone, CI, or a container. Nothing else in the package
hard-codes a path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    root: Path
    raw: dict[str, Any]

    @property
    def source(self) -> dict[str, Any]:
        return self.raw["source"]

    @property
    def resolution(self) -> dict[str, Any]:
        return self.raw["resolution"]

    @property
    def namespace(self) -> dict[str, str]:
        return self.raw["namespace"]

    def path(self, key: str) -> Path:
        """Absolute path for a key under ``paths``; directories are created on demand."""
        p = self.root / self.raw["paths"][key]
        if not p.suffix:
            p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def pdf(self) -> Path:
        return self.root / self.source["pdf"]


def load_config(path: Path | str | None = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Config(root=cfg_path.resolve().parent, raw=raw)
