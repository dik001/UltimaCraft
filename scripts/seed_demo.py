from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QColor, QImage
from sqlalchemy import select

from app.bootstrap import initialize_database
from app.models import Item
from app.paths import PATHS
from app.services.access import AccessController, AppMode
from app.services.builder_service import BuilderService, RecipeDraft
from app.services.catalog_service import CatalogService
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
    SubgroupInput,
)


def _find_or_create(rows, name: str, create):
    for row in rows():
        if row.name.casefold() == name.casefold():
            return row
    return create()


def _demo_image() -> None:
    destination = PATHS.resources / "demo_item.png"
    if destination.exists():
        return
    image = QImage(640, 400, QImage.Format_ARGB32)
    image.fill(QColor("#06143a"))
    accent = QColor("#0bb3aa")
    for x in range(24, 616):
        for offset in range(6):
            image.setPixelColor(x, 24 + offset, accent)
            image.setPixelColor(x, 369 + offset, accent)
    for y in range(24, 375):
        for offset in range(6):
            image.setPixelColor(24 + offset, y, accent)
            image.setPixelColor(610 + offset, y, accent)
    image.save(str(destination), "PNG")


def main() -> int:
    database = initialize_database()
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    images = ImageService(PATHS)
    items = ItemService(database.session_factory, access, images)
    recipes = RecipeService(database.session_factory, access)
    builder = BuilderService(items, recipes)

    with database.session_factory() as session:
        existing = session.scalar(select(Item).where(Item.name == "Сумка бронебойных 9 мм"))
        if existing is not None:
            print(f"Демонстрационный предмет уже существует: ID {existing.id}")
            database.dispose()
            return 0

    station = _find_or_create(
        references.list_stations,
        "Верстак",
        lambda: references.create_station(StationInput("Верстак", "Основная станция", 10)),
    )
    group = _find_or_create(
        references.list_groups,
        "Боеприпасы",
        lambda: references.create_group(GroupInput("Боеприпасы", 10)),
    )
    subgroup = _find_or_create(
        lambda: references.list_subgroups(group.id),
        "9 мм",
        lambda: references.create_subgroup(SubgroupInput(group.id, "9 мм", 10)),
    )
    weaponry = _find_or_create(
        references.list_skills,
        "Оружейное дело",
        lambda: references.create_skill(SkillInput("Оружейное дело")),
    )
    engineering = _find_or_create(
        references.list_skills,
        "Инженерия",
        lambda: references.create_skill(SkillInput("Инженерия")),
    )
    tools = _find_or_create(
        references.list_equipment,
        "Набор инструментов",
        lambda: references.create_equipment(EquipmentInput("Набор инструментов")),
    )

    def item_named(name: str):
        with database.session_factory() as session:
            return session.scalar(select(Item).where(Item.name == name))

    powder = item_named("Порох") or items.create_item(ItemInput("Порох", group.id))
    cases = item_named("Гильза 9 мм") or items.create_item(ItemInput("Гильза 9 мм", group.id, subgroup.id))
    metal = item_named("Металлолом") or items.create_item(ItemInput("Металлолом", group.id))
    _demo_image()
    result = builder.save(
        None,
        ItemInput(
            name="Сумка бронебойных 9 мм",
            group_id=group.id,
            subgroup_id=subgroup.id,
            rank="III",
            item_class="Боеприпасы",
            acquisition_codes=frozenset({"FIND", "TRADER", "AUCTION", "CRAFT"}),
            prices={"TRADER": Decimal("1200"), "AUCTION": Decimal("18900")},
        ),
        (
            RecipeDraft(
                None,
                RecipeInput(
                    craft_station_id=station.id,
                    output_quantity=Decimal("6"),
                    energy_cost=Decimal("6"),
                    ingredients=(
                        IngredientInput(powder.id, Decimal("3")),
                        IngredientInput(cases.id, Decimal("20")),
                        IngredientInput(metal.id, Decimal("2")),
                    ),
                    skill_requirements=(
                        SkillRequirementInput(weaponry.id, Decimal("6")),
                        SkillRequirementInput(engineering.id, Decimal("3")),
                    ),
                    skill_rewards=(SkillRewardInput(weaponry.id, Decimal("4")),),
                    equipment_requirements=(EquipmentRequirementInput(tools.id, Decimal("1")),),
                ),
            ),
        ),
        image_source=PATHS.resources / "demo_item.png",
    )
    print(f"Создан демонстрационный предмет: ID {result.item.id}")
    database.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
