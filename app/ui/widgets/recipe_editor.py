from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models import Recipe
from app.services.builder_service import RecipeDraft
from app.services.recipe_service import (
    EquipmentRequirementInput,
    IngredientInput,
    RecipeInput,
    SkillRequirementInput,
    SkillRewardInput,
)
from app.ui.widgets.inputs import DecimalSpinBox, IdComboBox


@dataclass(frozen=True, slots=True)
class RecipeLookups:
    stations: list[tuple[int, str]]
    items: list[tuple[int, str]]
    skills: list[tuple[int, str]]
    equipment: list[tuple[int, str]]


class LookupQuantityRow(QFrame):
    remove_requested = Signal(object)
    changed = Signal()

    def __init__(
        self,
        choices: list[tuple[int, str]],
        entity_id: int | None = None,
        quantity=None,
        *,
        allow_zero: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.combo = IdComboBox()
        self.combo.set_choices(choices, entity_id)
        self.quantity = DecimalSpinBox(minimum=0.0 if allow_zero else 0.0001)
        if quantity is not None:
            self.quantity.set_decimal(quantity)
        elif not allow_zero:
            self.quantity.setValue(1)
        self.remove_button = QPushButton("Удалить")
        self.remove_button.setObjectName("dangerButton")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.combo.currentIndexChanged.connect(self._notify_changed)
        self.combo.editTextChanged.connect(self._notify_changed)
        self.quantity.valueChanged.connect(self._notify_changed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.quantity)
        layout.addWidget(self.remove_button)

    def _notify_changed(self, *_args: object) -> None:
        """Normalize Qt signals carrying values to the argument-free form signal."""
        self.changed.emit()

    def set_admin_mode(self, enabled: bool) -> None:
        self.combo.setEnabled(enabled)
        self.quantity.setEnabled(enabled)
        self.remove_button.setVisible(enabled)


class DynamicRows(QWidget):
    changed = Signal()

    def __init__(
        self,
        title: str,
        add_text: str,
        choices: list[tuple[int, str]],
        *,
        allow_zero: bool = False,
    ) -> None:
        super().__init__()
        self.choices = choices
        self.allow_zero = allow_zero
        self.rows: list[LookupQuantityRow] = []
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        self.add_button = QPushButton(add_text)
        self.add_button.clicked.connect(lambda: self.add_row())
        header = QHBoxLayout()
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(self.add_button)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 3)
        layout.addLayout(header)
        layout.addLayout(self.rows_layout)

    def add_row(self, entity_id: int | None = None, quantity=None) -> LookupQuantityRow:
        row = LookupQuantityRow(
            self.choices,
            entity_id,
            quantity,
            allow_zero=self.allow_zero,
        )
        row.remove_requested.connect(self.remove_row)
        row.changed.connect(self.changed.emit)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self.changed.emit()
        return row

    def remove_row(self, row: LookupQuantityRow) -> None:
        if row in self.rows:
            self.rows.remove(row)
            self.rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
            self.changed.emit()

    def set_admin_mode(self, enabled: bool) -> None:
        self.add_button.setVisible(enabled)
        for row in self.rows:
            row.set_admin_mode(enabled)

    def refresh_choices(self, choices: list[tuple[int, str]]) -> None:
        self.choices = choices
        for row in self.rows:
            row.combo.refresh_choices(choices)


class RecipeEditorWidget(QFrame):
    remove_requested = Signal(object)
    changed = Signal()

    def __init__(
        self,
        number: int,
        lookups: RecipeLookups,
        recipe: Recipe | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("RecipeCard")
        self.setStyleSheet(
            "QFrame#RecipeCard { background:#262235; border:1px solid #3c3650; border-radius:10px; }"
        )
        self.recipe_id = recipe.id if recipe else None
        self.title_label = QLabel(f"РЕЦЕПТ №{number}")
        self.title_label.setObjectName("SectionTitle")
        self.remove_button = QPushButton("Удалить рецепт")
        self.remove_button.setObjectName("dangerButton")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.remove_button)

        self.station = IdComboBox()
        self.station.set_choices(lookups.stations, recipe.craft_station_id if recipe else None)
        self.output = DecimalSpinBox(minimum=0.0001)
        self.output.setValue(1)
        self.energy = DecimalSpinBox(minimum=0)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(75)
        self.active = QCheckBox("Рецепт активен")
        self.active.setChecked(True)
        if recipe:
            self.output.set_decimal(recipe.output_quantity)
            self.energy.set_decimal(recipe.energy_cost)
            self.notes.setPlainText(recipe.notes or "")
            self.active.setChecked(recipe.is_active)

        form = QFormLayout()
        form.addRow("Стол*", self.station)
        form.addRow("Результат за один крафт*", self.output)
        form.addRow("Затраты энергии*", self.energy)
        form.addRow("Заметки", self.notes)
        form.addRow("", self.active)

        self.ingredients = DynamicRows("РЕСУРСЫ ДЛЯ КРАФТА", "+ Добавить ресурс", lookups.items)
        self.requirements = DynamicRows(
            "ТРЕБОВАНИЯ К НАВЫКАМ", "+ Добавить навык", lookups.skills, allow_zero=True
        )
        self.rewards = DynamicRows(
            "ОПЫТ ЗА КРАФТ", "+ Добавить награду", lookups.skills, allow_zero=True
        )
        self.equipment = DynamicRows("ОБОРУДОВАНИЕ", "+ Добавить оборудование", lookups.equipment)

        if recipe:
            for line in recipe.ingredients:
                self.ingredients.add_row(line.item_id, line.quantity)
            for line in recipe.skill_requirements:
                self.requirements.add_row(line.skill_id, line.required_level)
            for line in recipe.skill_rewards:
                self.rewards.add_row(line.skill_id, line.experience_amount)
            for line in recipe.equipment_requirements:
                self.equipment.add_row(line.equipment_id, line.quantity)

        self.output.valueChanged.connect(self._notify_changed)
        self.energy.valueChanged.connect(self._notify_changed)
        self.notes.textChanged.connect(self._notify_changed)
        self.station.currentIndexChanged.connect(self._notify_changed)
        self.station.editTextChanged.connect(self._notify_changed)
        self.active.toggled.connect(self._notify_changed)
        for section in (self.ingredients, self.requirements, self.rewards, self.equipment):
            section.changed.connect(self._notify_changed)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(form)
        layout.addWidget(self.ingredients)
        layout.addWidget(self.requirements)
        layout.addWidget(self.rewards)
        layout.addWidget(self.equipment)

    def _notify_changed(self, *_args: object) -> None:
        """Normalize value-carrying Qt signals before propagating form changes."""
        self.changed.emit()

    def set_admin_mode(self, enabled: bool) -> None:
        self.remove_button.setVisible(enabled)
        self.station.setEnabled(enabled)
        self.output.setEnabled(enabled)
        self.energy.setEnabled(enabled)
        self.notes.setReadOnly(not enabled)
        self.active.setEnabled(enabled)
        for section in (self.ingredients, self.requirements, self.rewards, self.equipment):
            section.set_admin_mode(enabled)

    def refresh_lookups(self, lookups: RecipeLookups) -> None:
        """Use current DB lookups without discarding unsaved recipe rows."""
        self.station.refresh_choices(lookups.stations)
        self.ingredients.refresh_choices(lookups.items)
        self.requirements.refresh_choices(lookups.skills)
        self.rewards.refresh_choices(lookups.skills)
        self.equipment.refresh_choices(lookups.equipment)

    def collect(self) -> RecipeDraft:
        return RecipeDraft(
            self.recipe_id,
            RecipeInput(
                craft_station_id=self.station.required_id("Стол"),
                output_quantity=self.output.decimal_value(),
                energy_cost=self.energy.decimal_value(),
                notes=self.notes.toPlainText(),
                is_active=self.active.isChecked(),
                ingredients=tuple(
                    IngredientInput(row.combo.required_id("Ингредиент"), row.quantity.decimal_value())
                    for row in self.ingredients.rows
                ),
                skill_requirements=tuple(
                    SkillRequirementInput(row.combo.required_id("Навык"), row.quantity.decimal_value())
                    for row in self.requirements.rows
                ),
                skill_rewards=tuple(
                    SkillRewardInput(row.combo.required_id("Навык награды"), row.quantity.decimal_value())
                    for row in self.rewards.rows
                ),
                equipment_requirements=tuple(
                    EquipmentRequirementInput(
                        row.combo.required_id("Оборудование"), row.quantity.decimal_value()
                    )
                    for row in self.equipment.rows
                ),
            ),
        )
