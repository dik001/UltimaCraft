from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter, QDoubleSpinBox

from app.services.errors import ValidationError
from app.utils.text import normalized_key


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def parse_decimal(text: str, label: str, *, empty: Decimal | None = None) -> Decimal:
    clean = text.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not clean and empty is not None:
        return empty
    try:
        return Decimal(clean)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{label}: введите корректное число.") from exc


class DecimalSpinBox(QDoubleSpinBox):
    def __init__(self, *, minimum: float = 0.0, maximum: float = 999_999_999_999.0) -> None:
        super().__init__()
        self.setDecimals(4)
        self.setRange(minimum, maximum)
        self.setSingleStep(1.0)
        self.setGroupSeparatorShown(True)

    def decimal_value(self) -> Decimal:
        return Decimal(str(self.value()))

    def set_decimal(self, value: Decimal) -> None:
        self.setValue(float(value))

    def textFromValue(self, value: float) -> str:  # noqa: N802 - Qt API
        return format_decimal(Decimal(str(value)))


class IdComboBox(QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.completer().setFilterMode(Qt.MatchContains)
        self.completer().setCaseSensitivity(Qt.CaseInsensitive)

    def set_choices(
        self,
        choices: list[tuple[int | None, str]],
        current_id: int | None = None,
    ) -> None:
        self.blockSignals(True)
        self.clear()
        for entity_id, name in choices:
            self.addItem(name, entity_id)
        self.set_current_id(current_id)
        self.blockSignals(False)

    def refresh_choices(self, choices: list[tuple[int | None, str]]) -> None:
        """Refresh lookup rows while preserving a semantic ID or typed text.

        This also resolves text that has just been added to a reference table.
        A stale hidden ID is never reused when the visible text no longer
        matches the old selected row.
        """
        visible_text = self.currentText().strip()
        visible_key = normalized_key(visible_text)
        selected_id: int | None = None
        current_index = self.currentIndex()
        if (
            current_index >= 0
            and self.itemData(current_index) is not None
            and normalized_key(self.itemText(current_index)) == visible_key
        ):
            selected_id = int(self.itemData(current_index))

        was_blocked = self.blockSignals(True)
        self.clear()
        for entity_id, name in choices:
            self.addItem(name, entity_id)

        target_index = self.findData(selected_id) if selected_id is not None else -1
        if target_index < 0 and visible_key:
            matches = [
                index
                for index in range(self.count())
                if normalized_key(self.itemText(index)) == visible_key
            ]
            if len(matches) == 1:
                target_index = matches[0]
        self.setCurrentIndex(target_index)
        if target_index < 0:
            self.setEditText(visible_text)
        self.blockSignals(was_blocked)

    def set_current_id(self, entity_id: int | None) -> None:
        index = self.findData(entity_id)
        self.setCurrentIndex(index)
        if index < 0:
            self.setEditText("")

    def required_id(self, label: str) -> int:
        value = self.resolve_id(label, allow_unknown=False)
        assert value is not None
        return value

    def optional_id(self, label: str) -> int | None:
        visible_text = self.currentText().strip()
        if not visible_text:
            return None
        current_index = self.currentIndex()
        if (
            current_index >= 0
            and self.itemData(current_index) is None
            and normalized_key(self.itemText(current_index)) == normalized_key(visible_text)
        ):
            return None
        return self.required_id(label)

    def resolve_id(self, label: str, *, allow_unknown: bool) -> int | None:
        """Resolve visible text without ever reusing a stale hidden ID.

        Editable QComboBox keeps its previous currentData when users type over
        the displayed text.  An ID is valid only when that text still matches
        the selected row or exactly identifies one existing choice.
        """
        visible_text = self.currentText().strip()
        if not visible_text:
            if allow_unknown:
                return None
            raise ValidationError(f"{label}: выберите значение из справочника.")

        visible_key = normalized_key(visible_text)
        current_index = self.currentIndex()
        if (
            current_index >= 0
            and normalized_key(self.itemText(current_index)) == visible_key
            and self.itemData(current_index) is not None
        ):
            return int(self.itemData(current_index))

        matches = [
            index
            for index in range(self.count())
            if normalized_key(self.itemText(index)) == visible_key
            and self.itemData(index) is not None
        ]
        if len(matches) == 1:
            self.setCurrentIndex(matches[0])
            return int(self.itemData(matches[0]))
        if len(matches) > 1:
            raise ValidationError(
                f'{label}: найдено несколько значений «{visible_text}». '
                "Выберите нужную строку из списка."
            )
        if allow_unknown:
            return None
        raise ValidationError(
            f'{label}: значение «{visible_text}» отсутствует в справочнике.'
        )
