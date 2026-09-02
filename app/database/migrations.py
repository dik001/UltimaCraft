from __future__ import annotations

from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


def upgrade_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.resolve().as_posix()}")
    # The desktop process owns its logging configuration.  Alembic's CLI may
    # still configure console logging, but an in-process migration must not
    # replace the application's rotating file handler.
    config.attributes["configure_logger"] = False
    _repair_empty_initial_revision(database_path)
    command.upgrade(config, "head")


def _repair_empty_initial_revision(database_path: Path) -> None:
    """Repair databases created before the Alembic PRAGMA transaction fix.

    That defect could persist all initial SQLite DDL while rolling back only the
    version row.  The exact complete initial table set is verified before the
    revision is stamped, so an unrelated or partially-created database is never
    accepted silently.
    """
    if not database_path.exists():
        return
    expected = {
        "acquisition_method",
        "craft_station",
        "equipment",
        "item_group",
        "item_subgroup",
        "item",
        "item_use_effect",
        "item_acquisition",
        "item_price",
        "skill",
        "recipe",
        "recipe_ingredient",
        "recipe_skill_requirement",
        "recipe_skill_reward",
        "recipe_equipment_requirement",
    }
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "alembic_version" not in tables:
            return
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is not None:
            return
        if not expected <= tables:
            raise RuntimeError(
                "Обнаружена частично созданная схема без версии. "
                "Автоматическое обновление остановлено для защиты данных."
            )
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)",
            ("90b4640735d1",),
        )
        connection.commit()
