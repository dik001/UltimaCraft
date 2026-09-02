from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.errors import AccessDeniedError


class AppMode(StrEnum):
    VIEWER = "viewer"
    ADMIN = "admin"


@dataclass(slots=True)
class AccessController:
    mode: AppMode = AppMode.VIEWER

    @property
    def is_admin(self) -> bool:
        return self.mode is AppMode.ADMIN

    def require_admin(self) -> None:
        if not self.is_admin:
            raise AccessDeniedError("Изменение игровых данных доступно только администратору.")

