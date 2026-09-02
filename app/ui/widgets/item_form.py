from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QDir, QTemporaryFile, Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models import Item
from app.services.builder_service import (
    BuilderService,
    PendingGroupDraft,
    PendingItemDraft,
    PendingSubgroupDraft,
    RecipeDraft,
)
from app.services.catalog_service import CatalogService
from app.services.errors import ApplicationError, ValidationError
from app.services.item_service import ItemInput, ItemService, UseEffectInput
from app.services.price_service import PriceService
from app.services.recipe_service import RecipeService
from app.services.reference_service import ReferenceService
from app.ui.dialogs.quick_item_dialog import QuickItemDialog
from app.ui.widgets.inputs import DecimalSpinBox, IdComboBox, format_decimal, parse_decimal
from app.ui.widgets.recipe_editor import RecipeEditorWidget, RecipeLookups
from app.utils.text import normalized_key


LOGGER = logging.getLogger(__name__)


class EffectRow(QFrame):
    remove_requested = Signal(object)
    changed = Signal()

    def __init__(
        self,
        effect_type: str = "Энергия",
        value: Decimal = Decimal("0"),
        max_uses: int = 1,
    ) -> None:
        super().__init__()
        self.effect_type = QLineEdit(effect_type)
        self.value = DecimalSpinBox(minimum=-999_999_999)
        self.value.set_decimal(value)
        self.max_uses = QSpinBox()
        self.max_uses.setRange(1, 999_999)
        self.max_uses.setValue(max_uses)
        self.remove_button = QPushButton("Удалить")
        self.remove_button.setObjectName("dangerButton")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.effect_type.textChanged.connect(self._notify_changed)
        self.value.valueChanged.connect(self._notify_changed)
        self.max_uses.valueChanged.connect(self._notify_changed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(self.effect_type, 1)
        layout.addWidget(self.value)
        layout.addWidget(self.max_uses)
        layout.addWidget(self.remove_button)

    def _notify_changed(self, *_args: object) -> None:
        """Normalize Qt signals carrying values to the argument-free form signal."""
        self.changed.emit()

    def set_admin_mode(self, enabled: bool) -> None:
        self.effect_type.setReadOnly(not enabled)
        self.value.setEnabled(enabled)
        self.max_uses.setEnabled(enabled)
        self.remove_button.setVisible(enabled)


class ItemFormWidget(QWidget):
    saved = Signal(int)
    deleted = Signal()
    cancelled = Signal()

    def __init__(
        self,
        builder: BuilderService,
        items: ItemService,
        recipes: RecipeService,
        references: ReferenceService,
        catalog: CatalogService,
        price_service: PriceService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.builder = builder
        self.items = items
        self.recipe_service = recipes
        self.references = references
        self.catalog = catalog
        self.price_service = price_service
        self._admin_mode = True
        self.current_item_id: int | None = None
        self._dirty = False
        self._loading = False
        self._image_source: Path | None = None
        self._clipboard_temp: QTemporaryFile | None = None
        self._remove_image = False
        self._original_image_path: str | None = None
        self.effect_rows: list[EffectRow] = []
        self.recipe_widgets: list[RecipeEditorWidget] = []
        self._last_group_id: int | None = None
        self._last_subgroup_id: int | None = None
        self._last_station_id: int | None = None

        self.title = QLabel("НОВЫЙ ПРЕДМЕТ")
        self.title.setObjectName("TitleLabel")
        self.image_preview = QLabel("НЕТ ИЗОБРАЖЕНИЯ")
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setFixedSize(230, 170)
        self.image_preview.setFocusPolicy(Qt.ClickFocus)
        self.image_preview.setToolTip(
            "Нажмите сюда и используйте Ctrl+V или кнопку «Вставить скриншот»."
        )
        self.image_preview.setStyleSheet(
            "background:#211e2f; border:1px dashed #514a63; border-radius:10px; color:#817a91;"
        )
        self.choose_image_button = QPushButton("Выбрать / заменить")
        self.paste_image_button = QPushButton("Вставить скриншот")
        self.remove_image_button = QPushButton("Удалить изображение")
        self.choose_image_button.clicked.connect(self._choose_image)
        self.paste_image_button.clicked.connect(self._paste_image_from_clipboard)
        self.remove_image_button.clicked.connect(self._clear_image)
        self.paste_image_shortcut = QShortcut(QKeySequence.Paste, self.image_preview)
        self.paste_image_shortcut.setContext(Qt.WidgetShortcut)
        self.paste_image_shortcut.activated.connect(self._paste_image_from_clipboard)
        image_buttons = QVBoxLayout()
        image_buttons.addWidget(self.choose_image_button)
        image_buttons.addWidget(self.paste_image_button)
        image_buttons.addWidget(self.remove_image_button)
        image_buttons.addStretch()
        image_layout = QHBoxLayout()
        image_layout.addWidget(self.image_preview)
        image_layout.addLayout(image_buttons)
        image_layout.addStretch()

        self.name = QLineEdit()
        self.group = IdComboBox()
        self.subgroup = IdComboBox()
        self.rank = QLineEdit()
        self.item_class = QLineEdit()
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(85)
        self.active = QCheckBox("Предмет активен")
        self.active.setChecked(True)
        self.used_in_recipes = QLabel("Используется в крафтах: Нет")
        self.used_in_recipes.setObjectName("MutedLabel")
        core_form = QFormLayout()
        core_form.addRow("Название*", self.name)
        core_form.addRow("Группа*", self.group)
        core_form.addRow("Подгруппа", self.subgroup)
        core_form.addRow("Ранг", self.rank)
        core_form.addRow("Класс", self.item_class)
        core_form.addRow("Заметки", self.notes)
        core_form.addRow("", self.active)
        core_form.addRow("", self.used_in_recipes)
        core_group = QGroupBox("ОСНОВНОЕ")
        core_group.setLayout(core_form)

        self.consumable = QCheckBox("Предмет можно использовать")
        self.add_effect_button = QPushButton("+ Добавить эффект")
        self.add_effect_button.clicked.connect(lambda: self._add_effect())
        self.effects_layout = QVBoxLayout()
        effects_header = QHBoxLayout()
        effects_header.addWidget(self.consumable)
        effects_header.addStretch()
        effects_header.addWidget(self.add_effect_button)
        effects_box_layout = QVBoxLayout()
        effects_box_layout.addLayout(effects_header)
        effects_box_layout.addWidget(QLabel("Тип эффекта  |  Значение за использование  |  Использований"))
        effects_box_layout.addLayout(self.effects_layout)
        effects_group = QGroupBox("ИСПОЛЬЗОВАНИЕ")
        effects_group.setLayout(effects_box_layout)

        self.acquisition_checks: dict[str, QCheckBox] = {
            "FIND": QCheckBox("Найти в мире"),
            "TRADER": QCheckBox("Купить у скупщика"),
            "AUCTION": QCheckBox("Купить на аукционе"),
            "CRAFT": QCheckBox("Скрафтить"),
        }
        self.trader_price = QLineEdit()
        self.trader_price.setPlaceholderText("0")
        self.auction_price = QLineEdit()
        self.auction_price.setPlaceholderText("0")
        self.trader_updated = QLabel("")
        self.auction_updated = QLabel("")
        self.trader_updated.setObjectName("MutedLabel")
        self.auction_updated.setObjectName("MutedLabel")
        self.auction_edit_button = QPushButton("✎")
        self.auction_edit_button.setFixedWidth(38)
        self.auction_edit_button.setToolTip("Изменить текущую цену аукциона")
        auction_price_layout = QHBoxLayout()
        auction_price_layout.setContentsMargins(0, 0, 0, 0)
        auction_price_layout.addWidget(self.auction_price, 1)
        auction_price_layout.addWidget(self.auction_edit_button)
        auction_price_widget = QWidget()
        auction_price_widget.setLayout(auction_price_layout)
        acquisition_form = QFormLayout()
        acquisition_form.addRow(self.acquisition_checks["FIND"])
        acquisition_form.addRow(self.acquisition_checks["TRADER"], self.trader_price)
        acquisition_form.addRow("Обновлено", self.trader_updated)
        acquisition_form.addRow(self.acquisition_checks["AUCTION"], auction_price_widget)
        acquisition_form.addRow("Обновлено", self.auction_updated)
        acquisition_form.addRow(self.acquisition_checks["CRAFT"])
        acquisition_group = QGroupBox("СПОСОБЫ ПОЛУЧЕНИЯ И ЦЕНЫ")
        acquisition_group.setLayout(acquisition_form)

        recipes_header = QHBoxLayout()
        recipes_title = QLabel("РЕЦЕПТЫ")
        recipes_title.setObjectName("SectionTitle")
        self.add_recipe_button = QPushButton("+ Добавить рецепт")
        self.add_recipe_button.clicked.connect(self.add_recipe)
        recipes_header.addWidget(recipes_title)
        recipes_header.addStretch()
        recipes_header.addWidget(self.add_recipe_button)
        self.recipes_layout = QVBoxLayout()

        self.save_button = QPushButton("Сохранить")
        self.save_button.setObjectName("accentButton")
        self.save_new_button = QPushButton("Сохранить и создать следующий")
        self.cancel_button = QPushButton("Отменить изменения")
        self.duplicate_button = QPushButton("Дублировать")
        self.delete_button = QPushButton("Удалить предмет")
        self.delete_button.setObjectName("dangerButton")
        self.save_button.clicked.connect(self.save)
        self.save_new_button.clicked.connect(self.save_and_new)
        self.cancel_button.clicked.connect(self.cancel)
        self.duplicate_button.clicked.connect(self.duplicate)
        self.delete_button.clicked.connect(self.delete_current)
        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addWidget(self.save_new_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        actions.addWidget(self.duplicate_button)
        actions.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 18, 24)
        layout.addWidget(self.title)
        layout.addLayout(image_layout)
        layout.addWidget(core_group)
        layout.addWidget(effects_group)
        layout.addWidget(acquisition_group)
        layout.addLayout(recipes_header)
        layout.addLayout(self.recipes_layout)
        layout.addLayout(actions)
        layout.addStretch()

        self.group.currentIndexChanged.connect(self._group_changed)
        for widget in (self.name, self.rank, self.item_class, self.notes, self.trader_price, self.auction_price):
            widget.textChanged.connect(self._mark_dirty)
        self.group.currentIndexChanged.connect(self._mark_dirty)
        self.subgroup.currentIndexChanged.connect(self._mark_dirty)
        self.active.toggled.connect(self._mark_dirty)
        self.consumable.toggled.connect(self._consumable_changed)
        for code, checkbox in self.acquisition_checks.items():
            checkbox.toggled.connect(self._mark_dirty)
        self.acquisition_checks["TRADER"].toggled.connect(self.trader_price.setEnabled)
        self.acquisition_checks["AUCTION"].toggled.connect(self.auction_price.setEnabled)
        self.auction_edit_button.clicked.connect(self._enable_quick_auction_edit)
        self.auction_price.returnPressed.connect(self._save_quick_auction_price)
        self.new_item()

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def new_item(
        self,
        *,
        group_id: int | None = None,
        subgroup_id: int | None = None,
        station_id: int | None = None,
    ) -> None:
        self._loading = True
        self.current_item_id = None
        self._discard_clipboard_temp()
        self._image_source = None
        self._remove_image = False
        self._original_image_path = None
        self._refresh_lookups(group_id)
        self.name.clear()
        self.rank.clear()
        self.item_class.clear()
        self.notes.clear()
        self.active.setChecked(True)
        self.consumable.setChecked(False)
        self._clear_effect_rows()
        for checkbox in self.acquisition_checks.values():
            checkbox.setChecked(False)
        self.trader_price.clear()
        self.auction_price.clear()
        self.trader_updated.clear()
        self.auction_updated.clear()
        self._clear_recipe_widgets()
        self.title.setText("НОВЫЙ ПРЕДМЕТ")
        self.used_in_recipes.setText("Используется в крафтах: Нет")
        self.duplicate_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self._show_image(None)
        if group_id is not None:
            self.group.set_current_id(group_id)
            self._populate_subgroups(group_id, subgroup_id)
        self._last_station_id = station_id
        self._loading = False
        self._dirty = False
        self.set_admin_mode(self._admin_mode)

    def load_item(self, item_id: int) -> None:
        item = self.items.get_item(item_id)
        recipes = self.recipe_service.list_for_item(item_id)
        self._loading = True
        self.current_item_id = item.id
        self._discard_clipboard_temp()
        self._image_source = None
        self._remove_image = False
        self._original_image_path = item.image_path
        self._refresh_lookups(item.group_id)
        self.name.setText(item.name)
        self.group.set_current_id(item.group_id)
        self._populate_subgroups(item.group_id, item.subgroup_id)
        self.rank.setText(item.rank or "")
        self.item_class.setText(item.item_class or "")
        self.notes.setPlainText(item.notes or "")
        self.active.setChecked(item.is_active)
        self.consumable.setChecked(item.is_consumable)
        self._clear_effect_rows()
        for effect in item.use_effects:
            self._add_effect(effect.effect_type, effect.value, effect.max_uses)
        codes = {link.method.code for link in item.acquisitions}
        for code, checkbox in self.acquisition_checks.items():
            checkbox.setChecked(code in codes)
        prices = {price.price_type: price for price in item.prices}
        trader = prices.get("TRADER")
        auction = prices.get("AUCTION")
        self.trader_price.setText(format_decimal(trader.price) if trader else "")
        self.auction_price.setText(format_decimal(auction.price) if auction else "")
        self.trader_updated.setText(self._format_updated(trader.updated_at) if trader else "")
        self.auction_updated.setText(self._format_updated(auction.updated_at) if auction else "")
        self._clear_recipe_widgets()
        for recipe in recipes:
            self._add_recipe_widget(recipe)
        self.title.setText(item.name.upper())
        self.used_in_recipes.setText(
            f"Используется в крафтах: {'Да' if item.ingredient_uses else 'Нет'}"
        )
        self.duplicate_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self._show_image(self.items.images.resolve(item.image_path))
        self._loading = False
        self._dirty = False
        self.set_admin_mode(self._admin_mode)

    def add_recipe(self) -> None:
        if not self._admin_mode:
            return
        if not self.references.list_stations():
            QMessageBox.information(self, "Рецепт", "Сначала создайте хотя бы один стол в справочниках.")
            return
        self._add_recipe_widget(None, self._last_station_id)
        self._mark_dirty()

    def _add_recipe_widget(self, recipe=None, station_id: int | None = None) -> None:
        lookups = self._recipe_lookups()
        widget = RecipeEditorWidget(len(self.recipe_widgets) + 1, lookups, recipe)
        if recipe is None and station_id is not None:
            widget.station.set_current_id(station_id)
        widget.remove_requested.connect(self._remove_recipe_widget)
        widget.changed.connect(self._mark_dirty)
        self.recipe_widgets.append(widget)
        self.recipes_layout.addWidget(widget)

    def _remove_recipe_widget(self, widget: RecipeEditorWidget) -> None:
        if widget in self.recipe_widgets:
            self.recipe_widgets.remove(widget)
            self.recipes_layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
            self._mark_dirty()

    def save(self, *, notify: bool = True) -> int | None:
        temporary_entries: list[tuple[IdComboBox, int, str]] = []
        saved_to_database = False
        try:
            prepared = self._prepare_pending_ingredients()
            if prepared is None:
                return None
            pending_groups, pending_subgroups, pending_items, temporary_entries = prepared
            result = self.builder.save(
                self.current_item_id,
                self._collect_item(),
                tuple(widget.collect() for widget in self.recipe_widgets),
                image_source=self._image_source,
                remove_image=self._remove_image,
                pending_groups=pending_groups,
                pending_subgroups=pending_subgroups,
                pending_items=pending_items,
            )
            saved_to_database = True
            item_id = result.item.id
            self.load_item(item_id)
            self.saved.emit(item_id)
            if notify:
                QMessageBox.information(self, "Сохранено", "Предмет и рецепты сохранены.")
            return item_id
        except ApplicationError as exc:
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))
        except Exception as exc:
            LOGGER.exception("Не удалось сохранить карточку предмета")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить данные.\n\n{exc}")
        finally:
            if not saved_to_database:
                self._restore_temporary_ingredients(temporary_entries)
        return None

    def _prepare_pending_ingredients(
        self,
    ) -> tuple[
        tuple[PendingGroupDraft, ...],
        tuple[PendingSubgroupDraft, ...],
        tuple[PendingItemDraft, ...],
        list[tuple[IdComboBox, int, str]],
    ] | None:
        unknown: dict[str, tuple[str, list[IdComboBox]]] = {}
        for recipe in self.recipe_widgets:
            for row in recipe.ingredients.rows:
                if row.combo.resolve_id("Ингредиент", allow_unknown=True) is not None:
                    continue
                name = row.combo.currentText().strip()
                if not name:
                    raise ValidationError("Ингредиент: введите название ресурса.")
                key = normalized_key(name)
                if key not in unknown:
                    unknown[key] = (name, [])
                unknown[key][1].append(row.combo)

        if not unknown:
            return (), (), (), []

        default_group_id = self.group.required_id("Группа")
        default_subgroup_id = self.subgroup.optional_id("Подгруппа")
        groups = [(group.id, group.name) for group in self.references.list_groups()]
        subgroups = [
            (subgroup.id, subgroup.group_id, subgroup.name)
            for subgroup in self.references.list_subgroups()
        ]
        dialog = QuickItemDialog(
            [name for name, _combos in unknown.values()],
            groups,
            subgroups,
            default_group_id=default_group_id,
            default_subgroup_id=default_subgroup_id,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return None

        choice_by_key = {normalized_key(choice.name): choice for choice in dialog.choices()}
        pending_groups: list[PendingGroupDraft] = []
        pending_subgroups: list[PendingSubgroupDraft] = []
        pending_items: list[PendingItemDraft] = []
        temporary_entries: list[tuple[IdComboBox, int, str]] = []

        group_references: dict[str, int] = {}
        subgroup_references: dict[tuple[int, str], int] = {}
        for offset, (key, (typed_name, combos)) in enumerate(unknown.items(), start=1):
            temporary_id = -offset
            choice = choice_by_key[key]

            if choice.group_id is not None:
                group_id = choice.group_id
            else:
                group_key = normalized_key(choice.group_name)
                group_id = group_references.get(group_key, 0)
                if group_id == 0:
                    group_id = -(1_000_000 + len(pending_groups) + 1)
                    group_references[group_key] = group_id
                    pending_groups.append(PendingGroupDraft(group_id, choice.group_name))

            subgroup_id = choice.subgroup_id
            if subgroup_id is None and choice.subgroup_name is not None:
                subgroup_key = (group_id, normalized_key(choice.subgroup_name))
                subgroup_id = subgroup_references.get(subgroup_key, 0)
                if subgroup_id == 0:
                    subgroup_id = -(2_000_000 + len(pending_subgroups) + 1)
                    subgroup_references[subgroup_key] = subgroup_id
                    pending_subgroups.append(
                        PendingSubgroupDraft(subgroup_id, group_id, choice.subgroup_name)
                    )

            pending_items.append(
                PendingItemDraft(
                    temporary_id,
                    ItemInput(
                        name=choice.name,
                        group_id=group_id,
                        subgroup_id=subgroup_id,
                    ),
                )
            )
            for combo in combos:
                combo.addItem(choice.name, temporary_id)
                combo.setCurrentIndex(combo.count() - 1)
                temporary_entries.append((combo, temporary_id, typed_name))
        return (
            tuple(pending_groups),
            tuple(pending_subgroups),
            tuple(pending_items),
            temporary_entries,
        )

    @staticmethod
    def _restore_temporary_ingredients(
        entries: list[tuple[IdComboBox, int, str]],
    ) -> None:
        for combo, temporary_id, typed_name in entries:
            index = combo.findData(temporary_id)
            if index >= 0:
                combo.removeItem(index)
            combo.setCurrentIndex(-1)
            combo.setEditText(typed_name)

    def save_and_new(self) -> None:
        group_id = self.group.currentData()
        subgroup_id = self.subgroup.currentData()
        station_id = self.recipe_widgets[-1].station.currentData() if self.recipe_widgets else self._last_station_id
        if self.save(notify=False) is not None:
            self.new_item(
                group_id=int(group_id) if group_id is not None else None,
                subgroup_id=int(subgroup_id) if subgroup_id is not None else None,
                station_id=int(station_id) if station_id is not None else None,
            )
            self.name.setFocus()

    def cancel(self) -> None:
        if self.current_item_id is None:
            self.new_item(group_id=self.group.currentData(), subgroup_id=self.subgroup.currentData())
        else:
            self.load_item(self.current_item_id)
        self.cancelled.emit()

    def duplicate(self) -> None:
        if self.current_item_id is None:
            return
        try:
            duplicate = self.items.duplicate_item(self.current_item_id)
            self.load_item(duplicate.id)
            self.saved.emit(duplicate.id)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Дублирование", str(exc))

    def delete_current(self) -> None:
        if self.current_item_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f'Удалить предмет «{self.name.text().strip()}»?',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.items.delete_item(self.current_item_id)
            self.current_item_id = None
            self.new_item(group_id=self._last_group_id, subgroup_id=self._last_subgroup_id)
            self.deleted.emit()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Удаление заблокировано", str(exc))

    def _collect_item(self) -> ItemInput:
        group_id = self.group.required_id("Группа")
        effects = tuple(
            UseEffectInput(
                row.effect_type.text(),
                row.value.decimal_value(),
                row.max_uses.value(),
            )
            for row in self.effect_rows
        )
        codes = frozenset(
            code for code, checkbox in self.acquisition_checks.items() if checkbox.isChecked()
        )
        prices: dict[str, Decimal] = {}
        if self.acquisition_checks["TRADER"].isChecked() and self.trader_price.text().strip():
            prices["TRADER"] = parse_decimal(self.trader_price.text(), "Цена скупщика")
        if self.acquisition_checks["AUCTION"].isChecked() and self.auction_price.text().strip():
            prices["AUCTION"] = parse_decimal(self.auction_price.text(), "Цена аукциона")
        subgroup_id = self.subgroup.optional_id("Подгруппа")
        return ItemInput(
            name=self.name.text(),
            group_id=group_id,
            subgroup_id=subgroup_id,
            rank=self.rank.text(),
            item_class=self.item_class.text(),
            notes=self.notes.toPlainText(),
            is_active=self.active.isChecked(),
            is_consumable=self.consumable.isChecked(),
            effects=effects,
            acquisition_codes=codes,
            prices=prices,
        )

    def _refresh_lookups(self, current_group_id: int | None = None) -> None:
        groups = [(group.id, group.name) for group in self.references.list_groups()]
        self.group.set_choices(groups, current_group_id)
        self._populate_subgroups(current_group_id, None)

    def refresh_reference_lookups(self) -> None:
        """Refresh references after the manager closes, preserving form drafts."""
        was_loading = self._loading
        self._loading = True
        try:
            groups = [(group.id, group.name) for group in self.references.list_groups()]
            self.group.refresh_choices(groups)
            group_id = self.group.resolve_id("Группа", allow_unknown=True)

            subgroup_choices: list[tuple[int | None, str]] = [(None, "Без подгруппы")]
            if group_id is not None:
                subgroup_choices.extend(
                    (row.id, row.name)
                    for row in self.references.list_subgroups(group_id)
                )
            self.subgroup.refresh_choices(subgroup_choices)

            recipe_lookups = self._recipe_lookups()
            for widget in self.recipe_widgets:
                widget.refresh_lookups(recipe_lookups)
        finally:
            self._loading = was_loading

    def _populate_subgroups(self, group_id: int | None, current_id: int | None) -> None:
        choices: list[tuple[int | None, str]] = [(None, "Без подгруппы")]
        if group_id is not None:
            choices.extend(
                (row.id, row.name) for row in self.references.list_subgroups(int(group_id))
            )
        self.subgroup.set_choices(choices, current_id)

    def _group_changed(self) -> None:
        if self._loading:
            return
        group_id = self.group.currentData()
        self._populate_subgroups(int(group_id) if group_id is not None else None, None)
        self._mark_dirty()

    def _add_effect(
        self,
        effect_type: str = "Энергия",
        value: Decimal = Decimal("0"),
        max_uses: int = 1,
    ) -> None:
        row = EffectRow(effect_type, value, max_uses)
        row.remove_requested.connect(self._remove_effect)
        row.changed.connect(self._mark_dirty)
        self.effect_rows.append(row)
        self.effects_layout.addWidget(row)
        if not self._loading:
            self._mark_dirty()

    def _remove_effect(self, row: EffectRow) -> None:
        if row in self.effect_rows:
            self.effect_rows.remove(row)
            row.deleteLater()
            self._mark_dirty()

    def _clear_effect_rows(self) -> None:
        for row in self.effect_rows:
            row.deleteLater()
        self.effect_rows.clear()

    def _clear_recipe_widgets(self) -> None:
        for widget in self.recipe_widgets:
            widget.deleteLater()
        self.recipe_widgets.clear()

    def _recipe_lookups(self) -> RecipeLookups:
        return RecipeLookups(
            stations=[(row.id, row.name) for row in self.references.list_stations()],
            items=self.catalog.item_choices(),
            skills=[(row.id, row.name) for row in self.references.list_skills()],
            equipment=[(row.id, row.name) for row in self.references.list_equipment()],
        )

    def _choose_image(self) -> None:
        if not self._admin_mode:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение предмета",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not filename:
            return
        self._discard_clipboard_temp()
        self._image_source = Path(filename)
        self._remove_image = False
        self._show_image(self._image_source)
        self._mark_dirty()

    def _paste_image_from_clipboard(self) -> None:
        if not self._admin_mode:
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            QMessageBox.information(
                self,
                "Вставка изображения",
                "В буфере обмена нет изображения. Сначала сделайте или скопируйте скриншот.",
            )
            return

        temporary = QTemporaryFile(
            str(Path(QDir.tempPath()) / "craft_item_clipboard_XXXXXX.png"),
            self,
        )
        temporary.setAutoRemove(True)
        if not temporary.open():
            QMessageBox.warning(
                self,
                "Вставка изображения",
                "Не удалось создать временный файл для скриншота.",
            )
            return
        temporary_path = Path(temporary.fileName())
        temporary.close()
        if not image.save(str(temporary_path), "PNG"):
            temporary.remove()
            QMessageBox.warning(
                self,
                "Вставка изображения",
                "Не удалось подготовить изображение из буфера обмена.",
            )
            return

        self._discard_clipboard_temp()
        self._clipboard_temp = temporary
        self._image_source = temporary_path
        self._remove_image = False
        self._show_image(temporary_path)
        self._mark_dirty()

    def _clear_image(self) -> None:
        if not self._admin_mode:
            return
        self._discard_clipboard_temp()
        self._image_source = None
        self._remove_image = True
        self._show_image(None)
        self._mark_dirty()

    def _discard_clipboard_temp(self) -> None:
        temporary = self._clipboard_temp
        if temporary is None:
            return
        temporary_path = Path(temporary.fileName())
        self._clipboard_temp = None
        if self._image_source == temporary_path:
            self._image_source = None
        temporary.remove()

    def _show_image(self, path: Path | None) -> None:
        if path is not None and path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.image_preview.setPixmap(
                    pixmap.scaled(
                        self.image_preview.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                self.image_preview.setText("")
                return
        self.image_preview.setPixmap(QPixmap())
        self.image_preview.setText("НЕТ ИЗОБРАЖЕНИЯ")

    def _consumable_changed(self, checked: bool) -> None:
        self.add_effect_button.setEnabled(checked)
        if checked and not self.effect_rows and not self._loading:
            self._add_effect()
        self._mark_dirty()

    def _mark_dirty(self, *_args) -> None:
        if not self._loading and self._admin_mode:
            self._dirty = True

    def set_admin_mode(self, enabled: bool) -> None:
        self._admin_mode = enabled
        for widget in (self.name, self.rank, self.item_class, self.trader_price):
            widget.setReadOnly(not enabled)
        self.notes.setReadOnly(not enabled)
        self.group.setEnabled(enabled)
        self.subgroup.setEnabled(enabled)
        self.active.setEnabled(enabled)
        self.consumable.setEnabled(enabled)
        for checkbox in self.acquisition_checks.values():
            checkbox.setEnabled(enabled)
        for row in self.effect_rows:
            row.set_admin_mode(enabled)
        for recipe in self.recipe_widgets:
            recipe.set_admin_mode(enabled)
        for button in (
            self.choose_image_button,
            self.paste_image_button,
            self.remove_image_button,
            self.add_effect_button,
            self.add_recipe_button,
            self.save_button,
            self.save_new_button,
            self.cancel_button,
            self.duplicate_button,
            self.delete_button,
        ):
            button.setVisible(enabled)
        can_edit_auction = (
            not enabled
            and self.current_item_id is not None
            and self.acquisition_checks["AUCTION"].isChecked()
        )
        self.auction_edit_button.setVisible(can_edit_auction)
        self.auction_price.setReadOnly(True if not enabled else False)
        self._dirty = False

    def _enable_quick_auction_edit(self) -> None:
        if self._admin_mode or self.current_item_id is None:
            return
        self.auction_price.setReadOnly(False)
        self.auction_price.setFocus()
        self.auction_price.selectAll()

    def _save_quick_auction_price(self) -> None:
        if self._admin_mode or self.current_item_id is None or self.auction_price.isReadOnly():
            return
        try:
            value = parse_decimal(self.auction_price.text(), "Цена аукциона")
            self.price_service.update_auction_price(self.current_item_id, value)
            item_id = self.current_item_id
            self.load_item(item_id)
            self.saved.emit(item_id)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Цена аукциона", str(exc))

    @staticmethod
    def _format_updated(value) -> str:
        if value is None:
            return ""
        return value.astimezone().strftime("%d.%m.%Y %H:%M") if value.tzinfo else value.strftime("%d.%m.%Y %H:%M")
