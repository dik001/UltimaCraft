from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.session import Database
from app.paths import AppPaths
from app.services.access import AccessController, AppMode
from app.services.backup_service import BackupService
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService
from app.services.reference_service import GroupInput, ReferenceService


def test_backup_is_complete_and_integral(database: Database, tmp_path: Path) -> None:
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    paths = AppPaths.from_root(tmp_path / "workspace")
    items = ItemService(database.session_factory, access, ImageService(paths))
    group = references.create_group(GroupInput("Сохраняемая группа"))
    saved = items.create_item(ItemInput("Сохраняемый предмет", group.id))

    backup = BackupService(database.path, paths.backups).create_backup()
    assert backup.is_file()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT name FROM item WHERE id = ?", (saved.id,)).fetchone()[0] == "Сохраняемый предмет"
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() is not None


def test_missing_or_unsafe_image_resolves_to_placeholder(tmp_path: Path) -> None:
    paths = AppPaths.from_root(tmp_path / "workspace")
    images = ImageService(paths)
    assert images.resolve("data/images/items/missing.png") is None
    assert images.resolve("../../outside.png") is None

