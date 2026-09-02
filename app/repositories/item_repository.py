from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Item,
    ItemAcquisition,
    ItemPrice,
    ItemUseEffect,
    Recipe,
    RecipeIngredient,
)


class ItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, item_id: int) -> Item | None:
        return self.session.scalar(
            select(Item)
            .where(Item.id == item_id)
            .options(
                selectinload(Item.group),
                selectinload(Item.subgroup),
                selectinload(Item.use_effects),
                selectinload(Item.acquisitions).selectinload(ItemAcquisition.method),
                selectinload(Item.prices),
                selectinload(Item.ingredient_uses),
            )
        )

    def add(self, item: Item) -> Item:
        self.session.add(item)
        self.session.flush()
        return item

    def ingredient_use_count(self, item_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(RecipeIngredient).where(RecipeIngredient.item_id == item_id)
            )
            or 0
        )

    def recipe_count(self, item_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(Recipe).where(Recipe.result_item_id == item_id)
            )
            or 0
        )

    def image_reference_count(self, image_path: str) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(Item).where(Item.image_path == image_path)
            )
            or 0
        )

    def replace_owned_rows(
        self,
        item: Item,
        effects: list[ItemUseEffect],
        acquisitions: list[ItemAcquisition],
        prices: list[ItemPrice],
    ) -> None:
        item.use_effects.clear()
        item.acquisitions.clear()
        item.prices.clear()
        self.session.flush()
        item.use_effects.extend(effects)
        item.acquisitions.extend(acquisitions)
        item.prices.extend(prices)
        self.session.flush()
