from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

from app.services.errors import ValidationError


DEFAULT_ADMIN_PASSWORD = "admin"
PBKDF2_ITERATIONS = 240_000


class SettingsService:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.was_created = not path.exists()
        if self.was_created:
            self._write_password(DEFAULT_ADMIN_PASSWORD)

    def verify_admin_password(self, password: str) -> bool:
        data = self._read()
        salt = bytes.fromhex(data["admin_password_salt"])
        expected = bytes.fromhex(data["admin_password_hash"])
        iterations = int(data.get("pbkdf2_iterations", PBKDF2_ITERATIONS))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual, expected)

    def change_admin_password(self, current: str, new_password: str) -> None:
        if not self.verify_admin_password(current):
            raise ValidationError("Текущий пароль указан неверно.")
        if len(new_password) < 4:
            raise ValidationError("Новый пароль должен содержать не менее 4 символов.")
        self._write_password(new_password)

    def _write_password(self, password: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
        )
        payload = {
            "version": 1,
            "admin_password_salt": salt.hex(),
            "admin_password_hash": digest.hex(),
            "pbkdf2_iterations": PBKDF2_ITERATIONS,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError) as exc:
            raise ValidationError("Файл локальных настроек повреждён.") from exc

