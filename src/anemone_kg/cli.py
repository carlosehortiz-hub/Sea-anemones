"""Single CLI entry point: ``python -m anemone_kg run <stage>``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from anemone_kg.config import Config, load_config
from anemone_kg.logs import setup_logging

log = logging.getLogger("anemone_kg")

# Stages are registered in pipeline order. Each takes the Config and returns None.
STAGES: dict[str, Callable[[Config], None]] = {}


def stage(name: str) -> Callable[[Callable[[Config], None]], Callable[[Config], None]]:
    def register(fn: Callable[[Config], None]) -> Callable[[Config], None]:
        STAGES[name] = fn
        return fn

    return register


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="anemone_kg", description=__doc__)
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one pipeline stage, or 'all'")
    run.add_argument("stage", choices=[*STAGES, "all"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    cfg = load_config(args.config)
    todo = list(STAGES) if args.stage == "all" else [args.stage]
    for name in todo:
        log.info("=== stage: %s ===", name)
        STAGES[name](cfg)
    return 0
