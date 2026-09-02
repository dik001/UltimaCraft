from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from app.paths import AppPaths
from app.services.errors import ValidationError


ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


class ImageService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.ensure_directories()

    def import_item_image(self, source: Path) -> str:
        resolved = source.expanduser().resolve()
        if not resolved.is_file():
            raise ValidationError("Выбранный файл изображения не найден.")
        extension = resolved.suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError("Поддерживаются PNG, JPG, WEBP, BMP и GIF.")
        destination = self.paths.item_images / f"{uuid4().hex}{extension}"
        try:
            shutil.copy2(resolved, destination)
        except OSError as exc:
            raise ValidationError("Не удалось скопировать изображение в каталог приложения.") from exc
        return destination.relative_to(self.paths.root).as_posix()

    def duplicate_item_image(self, relative_path: str) -> str | None:
        source = self.resolve(relative_path)
        if source is None:
            return None
        return self.import_item_image(source)

    def resolve(self, relative_path: str | None) -> Path | None:
        if not relative_path:
            return None
        candidate = (self.paths.root / Path(relative_path)).resolve()
        if not candidate.is_relative_to(self.paths.root) or not candidate.is_file():
            return None
        return candidate

    def delete(self, relative_path: str | None) -> None:
        file_path = self.resolve(relative_path)
        if file_path is None:
            return
        if file_path.is_relative_to(self.paths.item_images.resolve()):
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass

