from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.database.session import Database
from app.models import RecipeIngredient
from app.paths import AppPaths
from app.services.access import AccessController, AppMode
from app.services.errors import AccessDeniedError, NotFoundError, ValidationError
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService
from app.services.recipe_service import (
    EquipmentRequirementInput,
    IngredientInput,
    RecipeInput,
    RecipeService,
    SkillRequirementInput,
    SkillRewardInput,
)
from app.services.reference_service import (
    EquipmentInput,
    GroupInput,
    ReferenceService,
    SkillInput,
    StationInput,
)


def test_complex_recipe_crud(database: Database, tmp_path: Path) -> None:
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(
        database.session_factory,
        access,
        ImageService(AppPaths.from_root(tmp_path / "workspace")),
    )
    recipes = RecipeService(database.session_factory, access)

    group = references.create_group(GroupInput("Боеприпасы"))
    station = references.create_station(StationInput("Верстак"))
    skill_a = references.create_skill(SkillInput("Оружейное дело"))
    skill_b = references.create_skill(SkillInput("Инженерия"))
    equipment = references.create_equipment(EquipmentInput("Набор инструментов"))
    result = items.create_item(ItemInput("Сумка бронебойных 9 мм", group.id))
    powder = items.create_item(ItemInput("Порох", group.id))
    cases = items.create_item(ItemInput("Гильза 9 мм", group.id))
    metal = items.create_item(ItemInput("Металлолом", group.id))

    created = recipes.create_recipe(
        result.id,
        RecipeInput(
            craft_station_id=station.id,
            output_quantity=Decimal("6"),
            energy_cost=Decimal("6.5"),
            ingredients=(
                IngredientInput(powder.id, Decimal("3")),
                IngredientInput(cases.id, Decimal("20")),
                IngredientInput(metal.id, Decimal("2.5")),
            ),
            skill_requirements=(
                SkillRequirementInput(skill_a.id, Decimal("6")),
                SkillRequirementInput(skill_b.id, Decimal("3")),
            ),
            skill_rewards=(SkillRewardInput(skill_a.id, Decimal("4.25")),),
            equipment_requirements=(
                EquipmentRequirementInput(equipment.id, Decimal("1")),
            ),
        ),
    )
    alternative = recipes.create_recipe(
        result.id,
        RecipeInput(station.id, Decimal("3"), Decimal("2"), ingredients=(IngredientInput(metal.id, Decimal("4")),)),
    )

    saved = recipes.get_recipe(created.id)
    assert saved.result_item.name == "Сумка бронебойных 9 мм"
    assert len(saved.ingredients) == 3
    assert {line.item.name for line in saved.ingredients} == {"Порох", "Гильза 9 мм", "Металлолом"}
    assert len(recipes.list_for_item(result.id)) == 2

    updated = recipes.update_recipe(
        created.id,
        RecipeInput(
            station.id,
            Decimal("8"),
            Decimal("7"),
            ingredients=(IngredientInput(powder.id, Decimal("2")),),
        ),
    )
    assert updated.output_quantity == Decimal("8.0000")
    assert len(updated.ingredients) == 1
    assert updated.ingredients[0].quantity == Decimal("2.0000")

    recipes.delete_recipe(alternative.id)
    with pytest.raises(NotFoundError):
        recipes.get_recipe(alternative.id)


def test_recipe_validation_and_viewer_guard(database: Database, tmp_path: Path) -> None:
    admin = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, admin)
    items = ItemService(
        database.session_factory,
        admin,
        ImageService(AppPaths.from_root(tmp_path / "workspace")),
    )
    recipes = RecipeService(database.session_factory, admin)
    group = references.create_group(GroupInput("Материалы"))
    station = references.create_station(StationInput("Плита"))
    result = items.create_item(ItemInput("Результат", group.id))
    ingredient = items.create_item(ItemInput("Ресурс", group.id))

    with pytest.raises(ValidationError, match="несколько раз"):
        recipes.create_recipe(
            result.id,
            RecipeInput(
                station.id,
                Decimal("1"),
                ingredients=(
                    IngredientInput(ingredient.id, Decimal("1")),
                    IngredientInput(ingredient.id, Decimal("2")),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="больше нуля"):
        recipes.create_recipe(result.id, RecipeInput(station.id, Decimal("0")))
    with pytest.raises(ValidationError, match="не существует"):
        recipes.create_recipe(
            result.id,
            RecipeInput(station.id, Decimal("1"), ingredients=(IngredientInput(999_999, Decimal("1")),)),
        )

    viewer = RecipeService(database.session_factory, AccessController(AppMode.VIEWER))
    with pytest.raises(AccessDeniedError):
        viewer.create_recipe(result.id, RecipeInput(station.id, Decimal("1")))

