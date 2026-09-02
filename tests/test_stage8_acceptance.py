from __future__ import annotations

import base64
import os
from decimal import Decimal
from pathlib import Path

from app.database.session import Database
from app.paths import AppPaths
from app.repositories.catalog_repository import ItemFilters
from app.services.access import AccessController, AppMode
from app.services.backup_service import BackupService
from app.services.builder_service import BuilderService, RecipeDraft
from app.services.catalog_service import CatalogService
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService
from app.services.price_service import PriceService
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


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_full_acceptance_scenario(database: Database, tmp_path: Path) -> None:
    paths = AppPaths.from_root(tmp_path / "workspace")
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    images = ImageService(paths)
    items = ItemService(database.session_factory, access, images)
    recipe_service = RecipeService(database.session_factory, access)
    builder = BuilderService(items, recipe_service)
    catalog = CatalogService(database.session_factory)

    station = references.create_station(StationInput("Верстак"))
    group = references.create_group(GroupInput("Боеприпасы"))
    subgroup = references.create_subgroup(SubgroupInput(group.id, "9 мм"))
    skill = references.create_skill(SkillInput("Оружейное дело"))
    equipment = references.create_equipment(EquipmentInput("Набор инструментов"))
    powder = items.create_item(ItemInput("Порох", group.id))
    cases = items.create_item(ItemInput("Гильза 9 мм", group.id, subgroup.id))
    image_source = tmp_path / "ammo.png"
    image_source.write_bytes(PNG_1X1)

    saved = builder.save(
        None,
        ItemInput(
            "Сумка бронебойных 9 мм",
            group.id,
            subgroup.id,
            rank="III",
            item_class="Боеприпасы",
            acquisition_codes=frozenset({"FIND", "TRADER", "AUCTION", "CRAFT"}),
            prices={"TRADER": Decimal("1200"), "AUCTION": Decimal("18900")},
        ),
        (
            RecipeDraft(
                None,
                RecipeInput(
                    station.id,
                    Decimal("6"),
                    Decimal("6"),
                    ingredients=(
                        IngredientInput(powder.id, Decimal("3")),
                        IngredientInput(cases.id, Decimal("20")),
                    ),
                    skill_requirements=(SkillRequirementInput(skill.id, Decimal("6")),),
                    skill_rewards=(SkillRewardInput(skill.id, Decimal("4")),),
                    equipment_requirements=(EquipmentRequirementInput(equipment.id, Decimal("1")),),
                ),
            ),
        ),
        image_source=image_source,
    )
    item = saved.item
    assert images.resolve(item.image_path) is not None
    assert len(saved.recipes) == 1
    recipe = saved.recipes[0]
    assert {line.item_id for line in recipe.ingredients} == {powder.id, cases.id}
    assert recipe.skill_requirements[0].skill_id == skill.id
    assert recipe.equipment_requirements[0].equipment_id == equipment.id
    assert {link.method.code for link in item.acquisitions} == {"FIND", "TRADER", "AUCTION", "CRAFT"}
    original_prices = {price.price_type: price.price for price in item.prices}
    assert original_prices["TRADER"] != original_prices["AUCTION"]
    assert catalog.list_items(ItemFilters(search="сумка"))[0].id == item.id
    assert catalog.list_items(ItemFilters(station_id=station.id))[0].id == item.id
    assert catalog.list_items(ItemFilters(used_in_recipes=True))

    access.mode = AppMode.VIEWER
    PriceService(database.session_factory).update_auction_price(item.id, Decimal("17500"))
    backup = BackupService(database.path, paths.backups).create_backup()
    assert backup.is_file()

    database.dispose()
    restarted = Database(database.path)
    persisted_items = ItemService(restarted.session_factory, access, images)
    persisted = persisted_items.get_item(item.id)
    persisted_prices = {price.price_type: price.price for price in persisted.prices}
    assert persisted.name == "Сумка бронебойных 9 мм"
    assert persisted_prices["AUCTION"] == Decimal("17500.0000")
    assert persisted_prices["TRADER"] == Decimal("1200.0000")
    assert len(RecipeService(restarted.session_factory, access).list_for_item(item.id)) == 1
    restarted.dispose()


def test_viewer_ui_hides_game_editing(database: Database, tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow

    paths = AppPaths.from_root(tmp_path / "ui-workspace")
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(database.session_factory, access, ImageService(paths))
    group = references.create_group(GroupInput("Каталог"))
    item = items.create_item(
        ItemInput(
            "Предмет Viewer",
            group.id,
            acquisition_codes=frozenset({"AUCTION"}),
            prices={"AUCTION": Decimal("10")},
        )
    )
    application = QApplication.instance() or QApplication([])
    window = MainWindow(database, paths)
    window.item_form.load_item(item.id)
    assert window.access.mode is AppMode.VIEWER
    assert window.item_form.name.isReadOnly()
    assert window.item_form.save_button.isHidden()
    assert window.add_item_button.isHidden()
    assert not window.item_form.auction_edit_button.isHidden()
    window.close()

