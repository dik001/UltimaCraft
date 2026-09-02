from __future__ import annotations

import logging
import os
import re
import sys
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from app.bootstrap import _install_exception_hook
from app.database.session import Database
from app.logging_config import configure_logging, flush_logging_handlers
from app.paths import AppPaths
from app.services.access import AccessController, AppMode
from app.services.builder_service import BuilderService, RecipeDraft
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService, UseEffectInput
from app.services.recipe_service import IngredientInput, RecipeInput, RecipeService
from app.services.reference_service import (
    GroupInput,
    ReferenceService,
    SkillInput,
    StationInput,
)
from app.ui.main_window import MainWindow
from app.ui.theme import APP_STYLESHEET


def test_recipe_editor_signals_save_and_viewer_controls(
    database: Database,
    tmp_path: Path,
) -> None:
    paths = AppPaths.from_root(tmp_path / "workspace")
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    images = ImageService(paths)
    items = ItemService(database.session_factory, access, images)
    recipes = RecipeService(database.session_factory, access)
    builder = BuilderService(items, recipes)
    group = references.create_group(GroupInput("Тестовая группа"))
    station = references.create_station(StationInput("Тестовый стол"))
    ingredient = items.create_item(ItemInput("Тестовый ресурс", group.id))
    result = builder.save(
        None,
        ItemInput(
            "Тестовый результат",
            group.id,
            is_consumable=True,
            effects=(UseEffectInput("Энергия", Decimal("2"), 1),),
        ),
        (
            RecipeDraft(
                None,
                RecipeInput(
                    station.id,
                    Decimal("1"),
                    Decimal("3"),
                    ingredients=(IngredientInput(ingredient.id, Decimal("2")),),
                ),
            ),
        ),
    )

    application = QApplication.instance() or QApplication([])
    window = MainWindow(database, paths)
    unhandled: list[tuple[str, str]] = []
    original_hook = sys.excepthook
    sys.excepthook = lambda kind, value, _traceback: unhandled.append(
        (kind.__name__, str(value))
    )
    try:
        window.access.mode = AppMode.ADMIN
        window._apply_mode()
        window.item_form.load_item(result.item.id)
        recipe = window.item_form.recipe_widgets[0]
        effect = window.item_form.effect_rows[0]

        recipe.output.setValue(7.5)
        recipe.energy.setValue(8.25)
        recipe.active.setChecked(False)
        recipe.ingredients.rows[0].quantity.setValue(4.5)
        effect.value.setValue(6.75)
        effect.max_uses.setValue(3)
        application.processEvents()

        assert unhandled == []
        assert window.item_form.has_unsaved_changes()
        assert window.item_form.save(notify=False) == result.item.id
        saved_recipe = recipes.list_for_item(result.item.id)[0]
        saved_item = items.get_item(result.item.id)
        assert saved_recipe.output_quantity == Decimal("7.5000")
        assert saved_recipe.energy_cost == Decimal("8.2500")
        assert saved_recipe.ingredients[0].quantity == Decimal("4.5000")
        assert saved_recipe.is_active is False
        assert saved_item.use_effects[0].value == Decimal("6.7500")
        assert saved_item.use_effects[0].max_uses == 3

        window.access.mode = AppMode.VIEWER
        window._apply_mode()
        application.processEvents()
        recipe = window.item_form.recipe_widgets[0]
        effect = window.item_form.effect_rows[0]
        assert recipe.remove_button.isHidden()
        assert recipe.ingredients.add_button.isHidden()
        assert recipe.ingredients.rows[0].remove_button.isHidden()
        assert effect.remove_button.isHidden()

        window.access.mode = AppMode.ADMIN
        window._apply_mode()
        recipe = window.item_form.recipe_widgets[0]
        window.item_form._remove_recipe_widget(recipe)
        application.processEvents()
        assert window.item_form.save(notify=False) == result.item.id
        assert recipes.list_for_item(result.item.id) == []
    finally:
        sys.excepthook = original_hook
        window.close()


def test_project_log_is_used_and_exception_details_are_visible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = AppPaths.from_root(tmp_path / "logging-workspace")
    paths.ensure_directories()
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)
    foreign = RotatingFileHandler(tmp_path / "foreign.log", encoding="utf-8")
    root.addHandler(foreign)
    shown_messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *_args, **_kwargs: shown_messages.append(str(_args[2])),
    )
    original_hook = sys.excepthook
    try:
        configure_logging(paths)
        _install_exception_hook(paths)
        try:
            raise RuntimeError("проверка журнала")
        except RuntimeError:
            kind, value, traceback = sys.exc_info()
            assert kind is not None and value is not None
            sys.excepthook(kind, value, traceback)
        flush_logging_handlers()

        contents = (paths.logs / "app.log").read_text(encoding="utf-8")
        assert "RuntimeError: проверка журнала" in contents
        assert shown_messages
        assert "RuntimeError: проверка журнала" in shown_messages[0]
    finally:
        sys.excepthook = original_hook
        for handler in list(root.handlers):
            if handler not in original_handlers:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(original_level)


def test_passive_text_widgets_have_no_background() -> None:
    widget_rule = re.search(r"QWidget\s*\{([^}]*)\}", APP_STYLESHEET)
    assert widget_rule is not None
    assert "background" not in widget_rule.group(1)
    assert "QLabel {\n    background-color: transparent;" in APP_STYLESHEET
    assert "QCheckBox {\n    background-color: transparent;" in APP_STYLESHEET


def test_combo_popup_uses_application_palette() -> None:
    assert "QComboBox QAbstractItemView, QListView {" in APP_STYLESHEET
    assert "background-color: #211e2f;" in APP_STYLESHEET
    assert "selection-background-color: #6840df;" in APP_STYLESHEET
    assert "selection-color: #fff1b8;" in APP_STYLESHEET


def test_new_reference_resolves_in_open_recipe_without_losing_draft(
    database: Database,
    tmp_path: Path,
) -> None:
    paths = AppPaths.from_root(tmp_path / "reference-refresh-workspace")
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(database.session_factory, access, ImageService(paths))
    recipes = RecipeService(database.session_factory, access)
    group = references.create_group(GroupInput("Боеприпасы"))
    station = references.create_station(StationInput("Верстак"))
    item = items.create_item(ItemInput("Патрон", group.id))
    recipes.create_recipe(item.id, RecipeInput(station.id, Decimal("1")))
    application = QApplication.instance() or QApplication([])

    window = MainWindow(database, paths)
    try:
        window.access.mode = AppMode.ADMIN
        window._apply_mode()
        window.item_form.load_item(item.id)
        recipe_widget = window.item_form.recipe_widgets[0]
        requirement = recipe_widget.requirements.add_row(quantity=1)
        reward = recipe_widget.rewards.add_row(quantity=100)
        requirement.combo.setEditText("Боеприпасы")
        reward.combo.setEditText("Боеприпасы")

        skill = references.create_skill(SkillInput("Боеприпасы"))
        window.item_form.refresh_reference_lookups()

        assert requirement.combo.required_id("Навык") == skill.id
        assert reward.combo.required_id("Навык награды") == skill.id
        assert requirement.quantity.value() == 1
        assert reward.quantity.value() == 100
        assert window.item_form.save(notify=False) == item.id
        saved = recipes.list_for_item(item.id)[0]
        assert saved.skill_requirements[0].skill_id == skill.id
        assert saved.skill_rewards[0].skill_id == skill.id
        application.processEvents()
    finally:
        window.close()


def test_clipboard_screenshot_is_previewed_and_saved(
    database: Database,
    tmp_path: Path,
) -> None:
    paths = AppPaths.from_root(tmp_path / "clipboard-workspace")
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(database.session_factory, access, ImageService(paths))
    group = references.create_group(GroupInput("Изображения"))
    item = items.create_item(ItemInput("Предмет со скриншотом", group.id))
    application = QApplication.instance() or QApplication([])
    screenshot = QImage(64, 48, QImage.Format.Format_ARGB32)
    screenshot.fill(QColor("#18c2cc"))
    application.clipboard().setImage(screenshot)

    window = MainWindow(database, paths)
    try:
        window.access.mode = AppMode.ADMIN
        window._apply_mode()
        window.item_form.load_item(item.id)
        window.item_form.paste_image_button.click()
        application.processEvents()

        temporary_path = window.item_form._image_source
        assert temporary_path is not None and temporary_path.is_file()
        assert temporary_path.suffix == ".png"
        assert window.item_form.image_preview.pixmap() is not None
        assert not window.item_form.image_preview.pixmap().isNull()
        assert window.item_form.has_unsaved_changes()

        assert window.item_form.save(notify=False) == item.id
        saved = items.get_item(item.id)
        saved_path = items.images.resolve(saved.image_path)
        assert saved.image_path is not None
        assert saved_path is not None and saved_path.is_file()
        assert saved_path.parent == paths.item_images
        assert not temporary_path.exists()

        window.access.mode = AppMode.VIEWER
        window._apply_mode()
        assert window.item_form.paste_image_button.isHidden()
    finally:
        application.clipboard().clear()
        window.close()
