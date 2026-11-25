"""Single CLI entry point: ``python -m anemone_kg run <stage>``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from anemone_kg.config import Config, load_config
from anemone_kg.logs import setup_logging

log = logging.getLogger("anemone_kg")

# Pipeline order is declared here, once. It must not depend on module import
# order: ruff sorts imports alphabetically, which once ran 'canonicalize'
# before 'extract' (see tests/test_cli.py).
PIPELINE = ("extract", "canonicalize", "resolve", "validate", "build", "shacl", "query")

STAGES: dict[str, Callable[[Config], None]] = {}


def stage(name: str) -> Callable[[Callable[[Config], None]], Callable[[Config], None]]:
    if name not in PIPELINE:
        raise ValueError(f"stage {name!r} is not declared in PIPELINE")

    def register(fn: Callable[[Config], None]) -> Callable[[Config], None]:
        STAGES[name] = fn
        return fn

    return register


def ordered_stages() -> list[str]:
    missing = [s for s in PIPELINE if s not in STAGES]
    if missing:
        raise RuntimeError(f"declared stages without an implementation: {missing}")
    return list(PIPELINE)


def _load_stages() -> None:
    import anemone_kg.stages  # noqa: F401  (registers stages via @stage)


def build_parser() -> argparse.ArgumentParser:
    _load_stages()
    p = argparse.ArgumentParser(prog="anemone_kg", description=__doc__)
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one pipeline stage, or 'all'")
    run.add_argument("stage", choices=[*PIPELINE, "all"])
    ep = sub.add_parser("endpoint", help="load the graph into a SPARQL endpoint / check queries")
    ep.add_argument("action", choices=["load", "check"])
    ep.add_argument("--url", default="http://localhost:7878")
    pa = sub.add_parser("paper", help="build the manuscript (HTML and PDF)")
    pa.add_argument("--no-pdf", action="store_true")
    pa.add_argument("--submission", action="store_true", help="journal submission files (DOCX)")
    pa.add_argument("--preprint", action="store_true", help="working-paper layout (one column)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    if args.command == "endpoint":
        from anemone_kg import endpoint

        extra = ["--config", args.config] if args.config else []
        return endpoint.main([args.action, "--url", args.url, *extra])
    if args.command == "paper":
        from anemone_kg.paper import build as paper

        extra = ["--config", args.config] if args.config else []
        flags = ["--no-pdf"] if args.no_pdf else []
        flags += ["--submission"] if args.submission else []
        flags += ["--preprint"] if args.preprint else []
        return paper.main(flags + extra)
    cfg = load_config(args.config)
    todo = ordered_stages() if args.stage == "all" else [args.stage]
    for name in todo:
        log.info("=== stage: %s ===", name)
        STAGES[name](cfg)
    return 0
