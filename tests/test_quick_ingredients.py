from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from app.database.session import Database
from app.paths import AppPaths
from app.services.access import AccessController, AppMode
from app.models import Item, ItemGroup, ItemSubgroup
from app.services.builder_service import (
    BuilderService,
    PendingGroupDraft,
    PendingItemDraft,
    PendingSubgroupDraft,
    RecipeDraft,
)
from app.services.catalog_service import CatalogService
from app.services.errors import ValidationError
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService
from app.services.recipe_service import IngredientInput, RecipeInput, RecipeService
from app.services.reference_service import GroupInput, ReferenceService, StationInput
from app.ui.dialogs.quick_item_dialog import QuickItemDialog
from app.ui.main_window import MainWindow
from app.ui.widgets.inputs import IdComboBox


def _services(database: Database, tmp_path: Path):
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(
        database.session_factory,
        access,
        ImageService(AppPaths.from_root(tmp_path / "service-workspace")),
    )
    recipes = RecipeService(database.session_factory, access)
    return access, references, items, recipes


def test_typed_new_ingredient_creates_item_and_real_fk(
    database: Database,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _access, references, items, recipes = _services(database, tmp_path)
    group = references.create_group(GroupInput("Боеприпасы"))
    station = references.create_station(StationInput("Верстак"))
    result = items.create_item(ItemInput("Сумка бронебойных 9 мм", group.id))
    recipes.create_recipe(result.id, RecipeInput(station.id, Decimal("1")))
    paths = AppPaths.from_root(tmp_path / "ui-workspace")
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QuickItemDialog, "exec", lambda _self: QDialog.Accepted)

    window = MainWindow(database, paths)
    try:
        window.access.mode = AppMode.ADMIN
        window._apply_mode()
        window.item_form.load_item(result.id)
        ingredient_row = window.item_form.recipe_widgets[0].ingredients.add_row()
        ingredient_row.combo.setEditText("Порох")
        ingredient_row.quantity.setValue(20)

        assert window.item_form.save(notify=False) == result.id
        saved_recipe = recipes.list_for_item(result.id)[0]
        choices = CatalogService(database.session_factory).item_choices()
        powder_id = next(item_id for item_id, name in choices if name == "Порох")
        assert saved_recipe.ingredients[0].item_id == powder_id
        assert saved_recipe.ingredients[0].item_id != result.id
        assert window.item_form.recipe_widgets[0].ingredients.rows[0].combo.currentText() == "Порох"
        application.processEvents()
    finally:
        window.close()


def test_stale_combo_id_is_never_used_for_typed_text() -> None:
    application = QApplication.instance() or QApplication([])
    combo = IdComboBox()
    combo.set_choices([(1, "Сумка бронебойных 9 мм")], 1)
    combo.setEditText("Порох")
    assert combo.resolve_id("Ингредиент", allow_unknown=True) is None
    with pytest.raises(ValidationError, match="отсутствует"):
        combo.required_id("Ингредиент")
    combo.set_choices([(1, "Сумка бронебойных 9 мм"), (2, "Порох")], 1)
    combo.setEditText("пОрОх")
    assert combo.required_id("Ингредиент") == 2
    application.processEvents()


def test_typed_group_and_subgroup_are_created_with_ingredient(
    database: Database,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _access, references, items, recipes = _services(database, tmp_path)
    default_group = references.create_group(GroupInput("Боеприпасы"))
    station = references.create_station(StationInput("Верстак"))
    result = items.create_item(ItemInput("Патрон", default_group.id))
    recipes.create_recipe(result.id, RecipeInput(station.id, Decimal("1")))
    application = QApplication.instance() or QApplication([])

    def enter_new_classification(dialog: QuickItemDialog) -> int:
        row = dialog._rows[0]
        row.group.setEditText("Материалы")
        row.subgroup.setEditText("Химические компоненты")
        return QDialog.Accepted

    monkeypatch.setattr(QuickItemDialog, "exec", enter_new_classification)
    window = MainWindow(database, AppPaths.from_root(tmp_path / "ui-workspace-new-refs"))
    try:
        window.access.mode = AppMode.ADMIN
        window._apply_mode()
        window.item_form.load_item(result.id)
        ingredient_row = window.item_form.recipe_widgets[0].ingredients.add_row()
        ingredient_row.combo.setEditText("Порох")
        ingredient_row.quantity.setValue(3)

        assert window.item_form.save(notify=False) == result.id
        with database.session_factory() as session:
            powder = session.scalar(select(Item).where(Item.name == "Порох"))
            group = session.scalar(select(ItemGroup).where(ItemGroup.name == "Материалы"))
            subgroup = session.scalar(
                select(ItemSubgroup).where(ItemSubgroup.name == "Химические компоненты")
            )
            assert powder is not None
            assert group is not None
            assert subgroup is not None
            assert subgroup.group_id == group.id
            assert powder.group_id == group.id
            assert powder.subgroup_id == subgroup.id
            assert recipes.list_for_item(result.id)[0].ingredients[0].item_id == powder.id
        application.processEvents()
    finally:
        window.close()


def test_pending_item_rolls_back_and_self_ingredient_is_allowed(
    database: Database,
    tmp_path: Path,
) -> None:
    access, references, items, recipes = _services(database, tmp_path)
    group = references.create_group(GroupInput("Материалы"))
    station = references.create_station(StationInput("Стол"))
    result = items.create_item(ItemInput("Результат", group.id))

    self_recipe = recipes.create_recipe(
        result.id,
        RecipeInput(
            station.id,
            Decimal("1"),
            ingredients=(IngredientInput(result.id, Decimal("1")),),
        ),
    )
    assert self_recipe.ingredients[0].item_id == result.id

    builder = BuilderService(items, recipes)
    with pytest.raises(ValidationError, match="отрицательными"):
        builder.save(
            result.id,
            ItemInput("Результат", group.id),
            (
                RecipeDraft(
                    self_recipe.id,
                    RecipeInput(
                        station.id,
                        Decimal("1"),
                        Decimal("-1"),
                        ingredients=(IngredientInput(-1, Decimal("2")),),
                    ),
                ),
            ),
            pending_groups=(PendingGroupDraft(-1_000_001, "Новая группа"),),
            pending_subgroups=(
                PendingSubgroupDraft(-2_000_001, -1_000_001, "Новая подгруппа"),
            ),
            pending_items=(
                PendingItemDraft(
                    -1,
                    ItemInput("Черновой ресурс", -1_000_001, -2_000_001),
                ),
            ),
        )
    assert all(
        name != "Черновой ресурс"
        for _item_id, name in CatalogService(database.session_factory).item_choices()
    )
    assert recipes.get_recipe(self_recipe.id).ingredients[0].item_id == result.id
    assert all(group.name != "Новая группа" for group in references.list_groups())
    assert all(
        subgroup.name != "Новая подгруппа" for subgroup in references.list_subgroups()
    )
