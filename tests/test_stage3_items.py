from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.database.session import Database
from app.paths import AppPaths
from app.services.access import AccessController, AppMode
from app.services.errors import DependencyError, ValidationError
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService, UseEffectInput
from app.services.reference_service import GroupInput, ReferenceService, SubgroupInput


@pytest.fixture
def item_services(database: Database, tmp_path: Path) -> tuple[ReferenceService, ItemService, AppPaths]:
    access = AccessController(AppMode.ADMIN)
    paths = AppPaths.from_root(tmp_path / "workspace")
    paths.ensure_directories()
    return (
        ReferenceService(database.session_factory, access),
        ItemService(database.session_factory, access, ImageService(paths)),
        paths,
    )


def test_item_aggregate_image_update_and_duplicate(
    item_services: tuple[ReferenceService, ItemService, AppPaths],
    tmp_path: Path,
) -> None:
    references, items, paths = item_services
    group = references.create_group(GroupInput("Боеприпасы"))
    subgroup = references.create_subgroup(SubgroupInput(group.id, "9 мм"))
    source = tmp_path / "item.png"
    source.write_bytes(b"not-a-real-png-but-a-valid-file-copy-test")

    created = items.create_item(
        ItemInput(
            name="Сумка бронебойных 9 мм",
            group_id=group.id,
            subgroup_id=subgroup.id,
            rank="III",
            item_class="Боеприпасы",
            is_consumable=True,
            effects=(UseEffectInput("Энергия", Decimal("12.5"), 3),),
            acquisition_codes=frozenset({"FIND", "TRADER", "AUCTION"}),
            prices={"TRADER": Decimal("1200"), "AUCTION": Decimal("18900.25")},
        ),
        source,
    )
    assert created.image_path is not None
    assert (paths.root / created.image_path).is_file()
    assert {link.method.code for link in created.acquisitions} == {"FIND", "TRADER", "AUCTION"}
    assert {price.price_type: price.price for price in created.prices} == {
        "TRADER": Decimal("1200.0000"),
        "AUCTION": Decimal("18900.2500"),
    }

    old_path = created.image_path
    updated = items.update_item(
        created.id,
        ItemInput(
            name="Сумка бронебойных патронов 9 мм",
            group_id=group.id,
            subgroup_id=subgroup.id,
            rank="IV",
            acquisition_codes=frozenset({"AUCTION"}),
            prices={"AUCTION": Decimal("17500")},
        ),
        remove_image=True,
    )
    assert updated.image_path is None
    assert not (paths.root / old_path).exists()
    assert updated.rank == "IV"

    duplicate = items.duplicate_item(updated.id)
    assert duplicate.id != updated.id
    assert duplicate.name.startswith("Копия —")
    assert duplicate.prices == []
    assert {link.method.code for link in duplicate.acquisitions} == {"AUCTION"}


def test_item_validation(item_services: tuple[ReferenceService, ItemService, AppPaths]) -> None:
    references, items, _ = item_services
    group_a = references.create_group(GroupInput("A"))
    group_b = references.create_group(GroupInput("B"))
    subgroup_b = references.create_subgroup(SubgroupInput(group_b.id, "B1"))

    with pytest.raises(ValidationError, match="Подгруппа"):
        items.create_item(ItemInput("Ошибка", group_a.id, subgroup_b.id))
    with pytest.raises(ValidationError, match="эффект"):
        items.create_item(ItemInput("Расходник", group_a.id, is_consumable=True))
    with pytest.raises(ValidationError, match="отключённого"):
        items.create_item(ItemInput("Цена", group_a.id, prices={"AUCTION": Decimal("1")}))
    with pytest.raises(ValidationError, match="отрицательной"):
        items.create_item(
            ItemInput(
                "Цена",
                group_a.id,
                acquisition_codes=frozenset({"AUCTION"}),
                prices={"AUCTION": Decimal("-1")},
            )
        )


def test_used_item_deletion_is_blocked(
    item_services: tuple[ReferenceService, ItemService, AppPaths],
    database: Database,
) -> None:
    references, items, _ = item_services
    group = references.create_group(GroupInput("Материалы"))
    ingredient = items.create_item(ItemInput("Порох", group.id))
    result = items.create_item(ItemInput("Патрон", group.id))

    from app.models import CraftStation, Recipe, RecipeIngredient

    with database.session_factory.begin() as session:
        station = CraftStation(name="Верстак")
        recipe = Recipe(
            result_item_id=result.id,
            craft_station=station,
            output_quantity=Decimal("1"),
            energy_cost=Decimal("0"),
            ingredients=[RecipeIngredient(item_id=ingredient.id, quantity=Decimal("2"))],
        )
        session.add(recipe)

    with pytest.raises(DependencyError, match="используется в 1 рецептах"):
        items.delete_item(ingredient.id)
    with pytest.raises(DependencyError, match="создано рецептов: 1"):
        items.delete_item(result.id)

