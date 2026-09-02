from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcquisitionMethod
from app.utils.text import normalized_key


SYSTEM_ACQUISITION_METHODS = (
    ("FIND", "Найти", 10),
    ("TRADER", "Скупщик", 20),
    ("AUCTION", "Аукцион", 30),
    ("CRAFT", "Скрафтить", 40),
)


def seed_acquisition_methods(session_factory: Callable[[], Session]) -> None:
    with session_factory.begin() as session:
        existing_codes = set(session.scalars(select(AcquisitionMethod.code)))
        for code, name, sort_order in SYSTEM_ACQUISITION_METHODS:
            if code not in existing_codes:
                session.add(
                    AcquisitionMethod(
                        code=code,
                        name=name,
                        name_key=normalized_key(name),
                        sort_order=sort_order,
                        is_active=True,
                    )
                )
