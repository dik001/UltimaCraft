from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.errors import ValidationError
from app.utils.text import normalized_key


@dataclass(frozen=True, slots=True)
class QuickItemChoice:
    name: str
    group_id: int | None
    group_name: str
    subgroup_id: int | None
    subgroup_name: str | None


@dataclass(slots=True)
class _QuickItemRow:
    name: str
    group: QComboBox
    subgroup: QComboBox


class QuickItemDialog(QDialog):
    """Choose classification for ingredient Items created during form save."""

    def __init__(
        self,
        names: list[str],
        groups: list[tuple[int, str]],
        subgroups: list[tuple[int, int, str]],
        *,
        default_group_id: int,
        default_subgroup_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Создание новых ресурсов")
        self.setMinimumWidth(760)
        self._groups = groups
        self._subgroups = subgroups
        self._rows: list[_QuickItemRow] = []

        explanation = QLabel(
            "Эти ресурсы ещё отсутствуют в базе. Выберите их группу и подгруппу — "
            "предметы и рецепт сохранятся одной операцией."
        )
        explanation.setWordWrap(True)

        self.table = QTableWidget(len(names), 3)
        self.table.setHorizontalHeaderLabels(("Новый ресурс", "Группа", "Подгруппа"))
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setMinimumHeight(min(420, 86 + len(names) * 44))

        for row_index, name in enumerate(names):
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_index, 0, name_item)

            group_combo = self._editable_combo()
            for group_id, group_name in groups:
                group_combo.addItem(group_name, group_id)
            group_index = group_combo.findData(default_group_id)
            group_combo.setCurrentIndex(max(0, group_index))

            subgroup_combo = self._editable_combo()
            row = _QuickItemRow(name, group_combo, subgroup_combo)
            self._rows.append(row)
            self._populate_subgroups(row, default_subgroup_id)
            group_combo.currentIndexChanged.connect(
                lambda _index, current_row=row: self._populate_subgroups(current_row)
            )
            group_combo.lineEdit().editingFinished.connect(
                lambda current_row=row: self._populate_subgroups(current_row)
            )
            self.table.setCellWidget(row_index, 1, group_combo)
            self.table.setCellWidget(row_index, 2, subgroup_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Создать и продолжить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def choices(self) -> tuple[QuickItemChoice, ...]:
        choices: list[QuickItemChoice] = []
        for row in self._rows:
            group_name = row.group.currentText().strip()
            if not group_name:
                raise ValidationError(f'Ресурс «{row.name}»: укажите группу.')
            group_id = self._existing_group_id(group_name)

            subgroup_name = row.subgroup.currentText().strip()
            if not subgroup_name or normalized_key(subgroup_name) == normalized_key(
                "Без подгруппы"
            ):
                subgroup_id = None
                subgroup_name = None
            else:
                subgroup_id = self._existing_subgroup_id(group_id, subgroup_name)

            choices.append(
                QuickItemChoice(
                    name=row.name,
                    group_id=group_id,
                    group_name=group_name,
                    subgroup_id=subgroup_id,
                    subgroup_name=subgroup_name,
                )
            )
        return tuple(choices)

    def _populate_subgroups(
        self,
        row: _QuickItemRow,
        current_id: int | None = None,
    ) -> None:
        group_id = self._existing_group_id(row.group.currentText())
        row.subgroup.blockSignals(True)
        row.subgroup.clear()
        row.subgroup.addItem("Без подгруппы", None)
        if group_id is not None:
            for subgroup_id, subgroup_group_id, subgroup_name in self._subgroups:
                if subgroup_group_id == int(group_id):
                    row.subgroup.addItem(subgroup_name, subgroup_id)
        index = row.subgroup.findData(current_id)
        row.subgroup.setCurrentIndex(max(0, index))
        row.subgroup.blockSignals(False)

    def _existing_group_id(self, name: str) -> int | None:
        key = normalized_key(name)
        return next(
            (group_id for group_id, group_name in self._groups if normalized_key(group_name) == key),
            None,
        )

    def _existing_subgroup_id(self, group_id: int | None, name: str) -> int | None:
        if group_id is None:
            return None
        key = normalized_key(name)
        return next(
            (
                subgroup_id
                for subgroup_id, subgroup_group_id, subgroup_name in self._subgroups
                if subgroup_group_id == group_id and normalized_key(subgroup_name) == key
            ),
            None,
        )

    def _accept_if_valid(self) -> None:
        try:
            self.choices()
        except ValidationError as exc:
            QMessageBox.warning(self, "Не удалось создать ресурсы", str(exc))
            return
        self.accept()

    @staticmethod
    def _editable_combo() -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        combo.completer().setFilterMode(Qt.MatchContains)
        combo.completer().setCaseSensitivity(Qt.CaseInsensitive)
        return combo
