from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    data: Path
    database: Path
    item_images: Path
    backups: Path
    logs: Path
    settings: Path
    resources: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            data=resolved / "data",
            database=resolved / "data" / "database.db",
            item_images=resolved / "data" / "images" / "items",
            backups=resolved / "backups",
            logs=resolved / "logs",
            settings=resolved / "data" / "settings.json",
            resources=resolved / "resources",
        )

    def ensure_directories(self) -> None:
        for path in (self.data, self.item_images, self.backups, self.logs, self.resources):
            path.mkdir(parents=True, exist_ok=True)


PATHS = AppPaths.from_root(Path(__file__).resolve().parent.parent)

