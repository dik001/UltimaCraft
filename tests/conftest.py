from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.database.migrations import upgrade_database
from app.database.seed import seed_acquisition_methods
from app.database.session import Database


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    path = tmp_path / "database.db"
    upgrade_database(path)
    db = Database(path)
    seed_acquisition_methods(db.session_factory)
    try:
        yield db
    finally:
        db.dispose()

