from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker


def sqlite_url(database_path: Path) -> URL:
    return URL.create("sqlite+pysqlite", database=str(database_path.resolve()))


def create_sqlite_engine(database_path: Path, *, echo: bool = False) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(sqlite_url(database_path), echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


class Database:
    def __init__(self, database_path: Path) -> None:
        self.path = database_path.resolve()
        self.engine = create_sqlite_engine(self.path)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def dispose(self) -> None:
        self.engine.dispose()

