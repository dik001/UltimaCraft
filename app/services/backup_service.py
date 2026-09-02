from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.services.errors import ApplicationError


class BackupService:
    def __init__(self, database_path: Path, backup_directory: Path) -> None:
        self.database_path = database_path
        self.backup_directory = backup_directory

    def create_backup(self) -> Path:
        if not self.database_path.is_file():
            raise ApplicationError("Файл базы данных не найден.")
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        destination = self.backup_directory / f"database_{stamp}.db"
        suffix = 1
        while destination.exists():
            destination = self.backup_directory / f"database_{stamp}_{suffix}.db"
            suffix += 1
        try:
            with sqlite3.connect(self.database_path) as source:
                integrity = source.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    raise ApplicationError(
                        "SQLite сообщает о повреждении базы. Резервная копия не создана."
                    )
                with sqlite3.connect(destination) as target:
                    source.backup(target)
                    copied_integrity = target.execute("PRAGMA integrity_check").fetchone()
                    if copied_integrity is None or copied_integrity[0] != "ok":
                        raise ApplicationError("Проверка созданной резервной копии не пройдена.")
        except ApplicationError:
            destination.unlink(missing_ok=True)
            raise
        except sqlite3.Error as exc:
            destination.unlink(missing_ok=True)
            raise ApplicationError("Не удалось создать резервную копию базы данных.") from exc
        return destination

