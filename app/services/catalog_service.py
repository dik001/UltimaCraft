from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item
from app.repositories.catalog_repository import CatalogRepository, ItemFilters, ItemSummary


class CatalogService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def list_items(self, filters: ItemFilters | None = None) -> list[ItemSummary]:
        with self.session_factory() as session:
            return CatalogRepository(session).list_items(filters or ItemFilters())

    def item_choices(self) -> list[tuple[int, str]]:
        with self.session_factory() as session:
            return list(session.execute(select(Item.id, Item.name).order_by(Item.name)).all())

    def distinct_ranks(self) -> list[str]:
        with self.session_factory() as session:
            return CatalogRepository(session).distinct_ranks()

    def distinct_classes(self) -> list[str]:
        with self.session_factory() as session:
            return CatalogRepository(session).distinct_classes()

