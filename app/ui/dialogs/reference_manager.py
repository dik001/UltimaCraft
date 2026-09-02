from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.errors import ApplicationError
from app.services.reference_service import (
    EquipmentInput,
    GroupInput,
    ReferenceService,
    SkillInput,
    StationInput,
    SubgroupInput,
)


class ReferenceEditorDialog(QDialog):
    def __init__(
        self,
        kind: str,
        service: ReferenceService,
        record: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.service = service
        self.record = record
        self.setWindowTitle("Новая запись" if record is None else "Изменить запись")
        self.setMinimumWidth(460)

        self.name = QLineEdit(getattr(record, "name", ""))
        self.sort_order = QSpinBox()
        self.sort_order.setRange(-999_999, 999_999)
        self.sort_order.setValue(getattr(record, "sort_order", 0))
        self.description = QTextEdit(getattr(record, "description", "") or "")
        self.description.setMaximumHeight(110)
        self.active = QCheckBox("Активна")
        self.active.setChecked(getattr(record, "is_active", True))
        self.image_path = QLineEdit(getattr(record, "image_path", "") or "")
        self.group = QComboBox()

        form = QFormLayout()
        form.addRow("Название*", self.name)
        if kind == "subgroups":
            for group in service.list_groups():
                self.group.addItem(group.name, group.id)
            current_group = getattr(record, "group_id", None)
            if current_group is not None:
                index = self.group.findData(current_group)
                self.group.setCurrentIndex(index)
            form.addRow("Группа*", self.group)
        if kind in {"stations", "groups", "subgroups"}:
            form.addRow("Порядок", self.sort_order)
        if kind in {"stations", "skills", "equipment"}:
            form.addRow("Описание", self.description)
            form.addRow("", self.active)
        if kind == "equipment":
            form.addRow("Путь изображения", self.image_path)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Проверка", "Название обязательно.")
            self.name.setFocus()
            return
        if self.kind == "subgroups" and self.group.currentData() is None:
            QMessageBox.warning(self, "Проверка", "Сначала создайте и выберите группу.")
            return
        self.accept()

    def payload(self) -> Any:
        common = {"name": self.name.text(), "description": self.description.toPlainText()}
        if self.kind == "stations":
            return StationInput(
                **common,
                sort_order=self.sort_order.value(),
                is_active=self.active.isChecked(),
            )
        if self.kind == "groups":
            return GroupInput(name=self.name.text(), sort_order=self.sort_order.value())
        if self.kind == "subgroups":
            return SubgroupInput(
                group_id=int(self.group.currentData()),
                name=self.name.text(),
                sort_order=self.sort_order.value(),
            )
        if self.kind == "skills":
            return SkillInput(**common, is_active=self.active.isChecked())
        return EquipmentInput(
            **common,
            image_path=self.image_path.text(),
            is_active=self.active.isChecked(),
        )


class ReferenceTab(QWidget):
    def __init__(self, kind: str, service: ReferenceService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.service = service
        self.records: list[Any] = []

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("ID", "Название", "Связь / описание", "Статус"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.edit_selected)

        add_button = QPushButton("+ Добавить")
        edit_button = QPushButton("Изменить")
        delete_button = QPushButton("Удалить")
        add_button.clicked.connect(self.add_record)
        edit_button.clicked.connect(self.edit_selected)
        delete_button.clicked.connect(self.delete_selected)

        controls = QHBoxLayout()
        controls.addWidget(add_button)
        controls.addWidget(edit_button)
        controls.addWidget(delete_button)
        controls.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(controls)
        self.refresh()

    def refresh(self) -> None:
        loaders: dict[str, Callable[[], list[Any]]] = {
            "stations": self.service.list_stations,
            "groups": self.service.list_groups,
            "subgroups": self.service.list_subgroups,
            "skills": self.service.list_skills,
            "equipment": self.service.list_equipment,
        }
        self.records = loaders[self.kind]()
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            relation = ""
            if self.kind == "subgroups":
                relation = record.group.name
            elif hasattr(record, "description"):
                relation = (record.description or "").replace("\n", " ")
            active = getattr(record, "is_active", True)
            values = (str(record.id), record.name, relation, "Активна" if active else "Отключена")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, record.id)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def selected_record(self) -> Any | None:
        row = self.table.currentRow()
        return self.records[row] if 0 <= row < len(self.records) else None

    def add_record(self) -> None:
        editor = ReferenceEditorDialog(self.kind, self.service, parent=self)
        if editor.exec() != QDialog.Accepted:
            return
        self._save(None, editor.payload())

    def edit_selected(self) -> None:
        record = self.selected_record()
        if record is None:
            QMessageBox.information(self, "Справочники", "Выберите запись.")
            return
        editor = ReferenceEditorDialog(self.kind, self.service, record=record, parent=self)
        if editor.exec() != QDialog.Accepted:
            return
        self._save(record.id, editor.payload())

    def _save(self, entity_id: int | None, payload: Any) -> None:
        create = getattr(self.service, f"create_{self.kind[:-1] if self.kind != 'equipment' else 'equipment'}")
        update = getattr(self.service, f"update_{self.kind[:-1] if self.kind != 'equipment' else 'equipment'}")
        try:
            create(payload) if entity_id is None else update(entity_id, payload)
            self.refresh()
            self.window().setWindowModified(True)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))

    def delete_selected(self) -> None:
        record = self.selected_record()
        if record is None:
            QMessageBox.information(self, "Справочники", "Выберите запись.")
            return
        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f'Удалить «{record.name}»?',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        method_name = self.kind[:-1] if self.kind != "equipment" else "equipment"
        try:
            getattr(self.service, f"delete_{method_name}")(record.id)
            self.refresh()
        except ApplicationError as exc:
            QMessageBox.warning(self, "Удаление заблокировано", str(exc))


class ReferenceManagerDialog(QDialog):
    def __init__(self, service: ReferenceService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Справочники")
        self.resize(900, 600)
        tabs = QTabWidget()
        tabs.addTab(ReferenceTab("stations", service), "Столы")
        tabs.addTab(ReferenceTab("groups", service), "Группы")
        tabs.addTab(ReferenceTab("subgroups", service), "Подгруппы")
        tabs.addTab(ReferenceTab("skills", service), "Навыки")
        tabs.addTab(ReferenceTab("equipment", service), "Оборудование")

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Значения справочников используются в карточках и рецептах."))
        layout.addWidget(tabs)
        layout.addWidget(close_button, alignment=Qt.AlignRight)

