from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.database.session import Database
from app.paths import AppPaths
from app.repositories.catalog_repository import ItemFilters
from app.services.access import AccessController, AppMode
from app.services.builder_service import BuilderService, RecipeDraft
from app.services.catalog_service import CatalogService
from app.services.errors import ValidationError
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService
from app.services.recipe_service import IngredientInput, RecipeInput, RecipeService
from app.services.reference_service import (
    GroupInput,
    ReferenceService,
    StationInput,
    SubgroupInput,
)


def test_atomic_builder_and_unicode_catalog_filters(database: Database, tmp_path: Path) -> None:
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(
        database.session_factory,
        access,
        ImageService(AppPaths.from_root(tmp_path / "workspace")),
    )
    recipe_service = RecipeService(database.session_factory, access)
    builder = BuilderService(items, recipe_service)
    catalog = CatalogService(database.session_factory)

    group = references.create_group(GroupInput("Боеприпасы"))
    subgroup = references.create_subgroup(SubgroupInput(group.id, "9 ММ"))
    station = references.create_station(StationInput("Верстак"))
    powder = items.create_item(ItemInput("Порох", group.id))
    result = builder.save(
        None,
        ItemInput(
            "Сумка Бронебойных 9 мм",
            group.id,
            subgroup.id,
            rank="III",
            item_class="Патроны",
            acquisition_codes=frozenset({"AUCTION", "CRAFT"}),
            prices={"AUCTION": Decimal("18900")},
        ),
        (
            RecipeDraft(
                None,
                RecipeInput(
                    station.id,
                    Decimal("6"),
                    Decimal("6"),
                    ingredients=(IngredientInput(powder.id, Decimal("3")),),
                ),
            ),
        ),
    )
    assert len(result.recipes) == 1
    assert result.recipes[0].ingredients[0].item_id == powder.id

    assert [row.id for row in catalog.list_items(ItemFilters(search="сумка бронебойных"))] == [result.item.id]
    assert [row.id for row in catalog.list_items(ItemFilters(search="БОЕПРИПАСЫ"))] == [powder.id, result.item.id]
    assert [row.id for row in catalog.list_items(ItemFilters(station_id=station.id))] == [result.item.id]
    assert [row.id for row in catalog.list_items(ItemFilters(craftable=True))] == [result.item.id]
    assert [row.id for row in catalog.list_items(ItemFilters(auction=True))] == [result.item.id]
    assert [row.id for row in catalog.list_items(ItemFilters(used_in_recipes=True))] == [powder.id]

    recipe_id = result.recipes[0].id
    with pytest.raises(ValidationError, match="несколько раз"):
        builder.save(
            result.item.id,
            ItemInput("НЕ ДОЛЖНО СОХРАНИТЬСЯ", group.id),
            (
                RecipeDraft(
                    recipe_id,
                    RecipeInput(
                        station.id,
                        Decimal("1"),
                        ingredients=(
                            IngredientInput(powder.id, Decimal("1")),
                            IngredientInput(powder.id, Decimal("2")),
                        ),
                    ),
                ),
            ),
        )
    assert items.get_item(result.item.id).name == "Сумка Бронебойных 9 мм"

