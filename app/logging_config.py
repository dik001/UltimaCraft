from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.paths import AppPaths


def configure_logging(paths: AppPaths) -> None:
    paths.ensure_directories()
    log_path = (paths.logs / "app.log").resolve()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(_targets_file(existing, log_path) for existing in root.handlers):
        return

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root.addHandler(handler)


def flush_logging_handlers() -> None:
    """Best-effort flush used before displaying a fatal UI error."""
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            continue


def _targets_file(handler: logging.Handler, path: Path) -> bool:
    if not isinstance(handler, logging.FileHandler):
        return False
    try:
        return Path(handler.baseFilename).resolve() == path
    except (OSError, TypeError, ValueError):
        return False
