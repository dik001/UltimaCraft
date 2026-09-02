from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, false, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    AcquisitionMethod,
    Item,
    ItemAcquisition,
    ItemGroup,
    ItemSubgroup,
    Recipe,
    RecipeIngredient,
)
from app.utils.text import normalized_key


@dataclass(frozen=True, slots=True)
class ItemFilters:
    search: str = ""
    station_id: int | None = None
    group_id: int | None = None
    subgroup_id: int | None = None
    rank: str | None = None
    item_class: str | None = None
    craftable: bool | None = None
    trader: bool | None = None
    auction: bool | None = None
    findable: bool | None = None
    used_in_recipes: bool | None = None


@dataclass(frozen=True, slots=True)
class ItemSummary:
    id: int
    name: str
    group_id: int
    group_name: str
    subgroup_id: int | None
    subgroup_name: str | None
    rank: str | None
    item_class: str | None
    craftable: bool
    used_in_recipes: bool


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_items(self, filters: ItemFilters, *, limit: int = 10_000) -> list[ItemSummary]:
        craft_exists = exists(select(Recipe.id).where(Recipe.result_item_id == Item.id))
        used_exists = exists(
            select(RecipeIngredient.id).where(RecipeIngredient.item_id == Item.id)
        )
        statement = (
            select(
                Item.id,
                Item.name,
                Item.group_id,
                ItemGroup.name.label("group_name"),
                Item.subgroup_id,
                ItemSubgroup.name.label("subgroup_name"),
                Item.rank,
                Item.item_class,
                craft_exists.label("craftable"),
                used_exists.label("used_in_recipes"),
            )
            .join(ItemGroup, Item.group_id == ItemGroup.id)
            .outerjoin(ItemSubgroup, Item.subgroup_id == ItemSubgroup.id)
        )
        if filters.search.strip():
            key = normalized_key(filters.search)
            statement = statement.where(
                or_(
                    Item.name_key.contains(key),
                    ItemGroup.name_key.contains(key),
                    ItemSubgroup.name_key.contains(key),
                )
            )
        if filters.station_id is not None:
            statement = statement.where(
                exists(
                    select(Recipe.id).where(
                        Recipe.result_item_id == Item.id,
                        Recipe.craft_station_id == filters.station_id,
                    )
                )
            )
        if filters.group_id is not None:
            statement = statement.where(Item.group_id == filters.group_id)
        if filters.subgroup_id is not None:
            statement = statement.where(Item.subgroup_id == filters.subgroup_id)
        if filters.rank:
            statement = statement.where(Item.rank == filters.rank)
        if filters.item_class:
            statement = statement.where(Item.item_class == filters.item_class)
        statement = self._boolean_exists(statement, craft_exists, filters.craftable)
        statement = self._boolean_exists(statement, used_exists, filters.used_in_recipes)
        for code, value in (
            ("TRADER", filters.trader),
            ("AUCTION", filters.auction),
            ("FIND", filters.findable),
        ):
            acquisition_exists = exists(
                select(ItemAcquisition.id)
                .join(AcquisitionMethod, ItemAcquisition.method_id == AcquisitionMethod.id)
                .where(ItemAcquisition.item_id == Item.id, AcquisitionMethod.code == code)
            )
            statement = self._boolean_exists(statement, acquisition_exists, value)
        rows = self.session.execute(
            statement.order_by(ItemGroup.sort_order, ItemGroup.name, ItemSubgroup.sort_order, ItemSubgroup.name, Item.name)
            .limit(limit)
        ).all()
        return [ItemSummary(*row) for row in rows]

    def distinct_ranks(self) -> list[str]:
        return list(
            self.session.scalars(
                select(Item.rank).where(Item.rank.is_not(None), Item.rank != "").distinct().order_by(Item.rank)
            )
        )

    def distinct_classes(self) -> list[str]:
        return list(
            self.session.scalars(
                select(Item.item_class)
                .where(Item.item_class.is_not(None), Item.item_class != "")
                .distinct()
                .order_by(Item.item_class)
            )
        )

    @staticmethod
    def _boolean_exists(statement, expression, value: bool | None):
        if value is True:
            return statement.where(expression)
        if value is False:
            return statement.where(~expression)
        return statement

