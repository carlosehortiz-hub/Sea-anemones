"""Stage logging with record counts, so data loss between stages is visible."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt="%H:%M:%S")
    # pdfminer logs a harmless warning per page about a 2-component colour space.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)


def log_counts(logger: logging.Logger, stage: str, n_in: int, n_out: int, note: str = "") -> None:
    """Log in/out counts; a drop is logged as WARNING so it cannot pass silently."""
    dropped = n_in - n_out
    msg = f"[{stage}] in={n_in} out={n_out} dropped={dropped}"
    if note:
        msg += f" ({note})"
    (logger.warning if dropped > 0 else logger.info)(msg)
