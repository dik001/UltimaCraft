from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.database.session import Database
from app.models import (
    AcquisitionMethod,
    CraftStation,
    Item,
    ItemAcquisition,
    ItemGroup,
    ItemSubgroup,
    Recipe,
    RecipeIngredient,
)


EXPECTED_TABLES = {
    "acquisition_method",
    "craft_station",
    "equipment",
    "item_group",
    "item_subgroup",
    "item",
    "item_use_effect",
    "item_acquisition",
    "item_price",
    "skill",
    "recipe",
    "recipe_ingredient",
    "recipe_skill_requirement",
    "recipe_skill_reward",
    "recipe_equipment_requirement",
}


def test_migration_and_system_acquisition_methods(database: Database) -> None:
    assert EXPECTED_TABLES <= set(inspect(database.engine).get_table_names())
    with database.session_factory() as session:
        codes = set(session.scalars(select(AcquisitionMethod.code)))
        assert codes == {"FIND", "TRADER", "AUCTION", "CRAFT"}
        assert session.scalar(text("PRAGMA foreign_keys")) == 1


def test_relations_allow_alternative_recipes_and_methods(database: Database) -> None:
    with database.session_factory.begin() as session:
        group = ItemGroup(name="Боеприпасы", sort_order=10)
        subgroup = ItemSubgroup(name="9 мм", sort_order=10, group=group)
        station = CraftStation(name="Верстак", sort_order=10, is_active=True)
        result = Item(name="Сумка бронебойных 9 мм", group=group, subgroup=subgroup)
        powder = Item(name="Порох", group=group)
        metal = Item(name="Металлолом", group=group)
        session.add_all((station, result, powder, metal))
        session.flush()

        result.recipes.extend(
            (
                Recipe(
                    craft_station=station,
                    output_quantity=Decimal("6"),
                    energy_cost=Decimal("6"),
                    ingredients=[RecipeIngredient(item=powder, quantity=Decimal("3"))],
                ),
                Recipe(
                    craft_station=station,
                    output_quantity=Decimal("3"),
                    energy_cost=Decimal("2.5"),
                    ingredients=[RecipeIngredient(item=metal, quantity=Decimal("1.5"))],
                ),
            )
        )

        methods = {
            method.code: method
            for method in session.scalars(select(AcquisitionMethod)).all()
        }
        result.acquisitions.extend(
            (
                ItemAcquisition(method=methods["FIND"]),
                ItemAcquisition(method=methods["AUCTION"]),
                ItemAcquisition(method=methods["CRAFT"]),
            )
        )

    with database.session_factory() as session:
        saved = session.scalar(select(Item).where(Item.name == "Сумка бронебойных 9 мм"))
        assert saved is not None
        assert len(saved.recipes) == 2
        assert {link.method.code for link in saved.acquisitions} == {"FIND", "AUCTION", "CRAFT"}
        assert {line.item.name for recipe in saved.recipes for line in recipe.ingredients} == {
            "Порох",
            "Металлолом",
        }


def test_ingredient_cannot_reference_missing_item(database: Database) -> None:
    with database.session_factory.begin() as session:
        group = ItemGroup(name="Материалы")
        station = CraftStation(name="Лаборатория")
        result = Item(name="Результат", group=group)
        recipe = Recipe(
            result_item=result,
            craft_station=station,
            output_quantity=Decimal("1"),
            energy_cost=Decimal("0"),
        )
        session.add(recipe)
        session.flush()
        recipe_id = recipe.id

    with pytest.raises(IntegrityError):
        with database.session_factory.begin() as session:
            session.add(
                RecipeIngredient(
                    recipe_id=recipe_id,
                    item_id=999_999,
                    quantity=Decimal("1"),
                )
            )


def test_deleting_used_ingredient_is_restricted(database: Database) -> None:
    with database.session_factory.begin() as session:
        group = ItemGroup(name="Компоненты")
        station = CraftStation(name="Плита")
        result = Item(name="Готовый предмет", group=group)
        ingredient = Item(name="Компонент", group=group)
        recipe = Recipe(
            result_item=result,
            craft_station=station,
            output_quantity=Decimal("1"),
            energy_cost=Decimal("0"),
            ingredients=[RecipeIngredient(item=ingredient, quantity=Decimal("1"))],
        )
        session.add(recipe)
        session.flush()
        ingredient_id = ingredient.id

    with pytest.raises(IntegrityError):
        with database.session_factory.begin() as session:
            session.delete(session.get(Item, ingredient_id))

