from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database.session import Database
from app.paths import AppPaths
from app.repositories.catalog_repository import ItemFilters
from app.services.access import AccessController, AppMode
from app.services.builder_service import BuilderService
from app.services.backup_service import BackupService
from app.services.catalog_service import CatalogService
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.services.price_service import PriceService
from app.services.recipe_service import RecipeService
from app.services.reference_service import ReferenceService
from app.services.settings_service import DEFAULT_ADMIN_PASSWORD, SettingsService
from app.services.errors import ApplicationError
from app.ui.dialogs.reference_manager import ReferenceManagerDialog
from app.ui.theme import APP_STYLESHEET
from app.ui.widgets.item_form import ItemFormWidget


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, database: Database, paths: AppPaths) -> None:
        super().__init__()
        self.database = database
        self.paths = paths
        self.access = AccessController(AppMode.VIEWER)
        self.settings_service = SettingsService(paths.settings)
        self.reference_service = ReferenceService(database.session_factory, self.access)
        self.image_service = ImageService(paths)
        self.item_service = ItemService(database.session_factory, self.access, self.image_service)
        self.recipe_service = RecipeService(database.session_factory, self.access)
        self.catalog_service = CatalogService(database.session_factory)
        self.price_service = PriceService(database.session_factory)
        self.builder_service = BuilderService(self.item_service, self.recipe_service)
        self.backup_service = BackupService(paths.database, paths.backups)
        self._tree_item_by_id: dict[int, QTreeWidgetItem] = {}
        self._previous_tree_item: QTreeWidgetItem | None = None
        self._restoring_selection = False

        self.setWindowTitle("База игровых предметов — Database Builder")
        self.resize(1500, 900)
        self.setMinimumSize(1050, 680)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_menu()
        self._build_ui()
        self._connect_filters()
        self.refresh_filter_values()
        self.reload_catalog()
        self._apply_mode()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Файл")
        self.backup_action = QAction("Создать резервную копию базы", self)
        self.open_data_action = QAction("Открыть папку данных", self)
        self.backup_action.triggered.connect(self._create_backup)
        self.open_data_action.triggered.connect(self._open_data_folder)
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(self.backup_action)
        file_menu.addAction(self.open_data_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        settings_menu = self.menuBar().addMenu("Настройки")
        change_password = QAction("Сменить пароль администратора", self)
        change_password.triggered.connect(self._change_admin_password)
        settings_menu.addAction(change_password)

    def _build_ui(self) -> None:
        brand_title = QLabel("CRAFT\nDATABASE")
        brand_title.setObjectName("BrandTitle")
        brand_subtitle = QLabel("ITEMS & RECIPES")
        brand_subtitle.setObjectName("BrandSubtitle")
        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(20, 18, 20, 18)
        brand_layout.addWidget(brand_title)
        brand_layout.addStretch()
        brand_layout.addWidget(brand_subtitle)
        brand_card = QFrame()
        brand_card.setObjectName("BrandCard")
        brand_card.setMinimumHeight(120)
        brand_card.setLayout(brand_layout)

        catalog_title = QLabel("КАТАЛОГ")
        catalog_title.setObjectName("SidebarSection")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(260)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        self.result_count = QLabel("0 предметов")
        self.result_count.setObjectName("MutedLabel")
        mode_title = QLabel("РЕЖИМ ДОСТУПА")
        mode_title.setObjectName("SidebarSection")
        self.mode_button = QPushButton("Режим: Администратор")
        self.mode_button.setObjectName("ModeButton")
        self.mode_button.clicked.connect(self._toggle_mode)

        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(12, 12, 12, 14)
        sidebar_layout.setSpacing(10)
        sidebar_layout.addWidget(brand_card)
        sidebar_layout.addWidget(catalog_title)
        sidebar_layout.addWidget(self.tree, 1)
        sidebar_layout.addWidget(self.result_count)
        sidebar_layout.addWidget(mode_title)
        sidebar_layout.addWidget(self.mode_button)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(285)
        sidebar.setMaximumWidth(390)
        sidebar.setLayout(sidebar_layout)

        page_title = QLabel("Обзор базы")
        page_title.setObjectName("PageTitle")
        self.mode_status = QLabel("VIEWER · ТОЛЬКО ЧТЕНИЕ")
        self.mode_status.setObjectName("ModeStatus")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по предмету, группе или подгруппе…")
        self.search.setClearButtonEnabled(True)
        self.add_item_button = QPushButton("+ Предмет")
        self.add_item_button.setObjectName("accentButton")
        self.add_recipe_button = QPushButton("+ Рецепт")
        self.references_button = QPushButton("Справочники")
        self.top_mode_button = QPushButton("Войти как администратор")
        self.top_mode_button.setObjectName("TopModeButton")
        self.add_item_button.clicked.connect(self.new_item)
        self.add_recipe_button.clicked.connect(self.add_recipe)
        self.references_button.clicked.connect(self.open_references)
        self.top_mode_button.clicked.connect(self._toggle_mode)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(10)
        top_layout.addWidget(page_title)
        top_layout.addWidget(self.mode_status)
        top_layout.addWidget(self.search, 1)
        top_layout.addWidget(self.add_item_button)
        top_layout.addWidget(self.add_recipe_button)
        top_layout.addWidget(self.references_button)
        top_layout.addWidget(self.top_mode_button)
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setLayout(top_layout)

        self.station_filter = QComboBox()
        self.group_filter = QComboBox()
        self.subgroup_filter = QComboBox()
        self.rank_filter = QComboBox()
        self.class_filter = QComboBox()
        self.craft_filter = self._boolean_combo()
        self.trader_filter = self._boolean_combo()
        self.auction_filter = self._boolean_combo()
        self.find_filter = self._boolean_combo()
        self.used_filter = self._boolean_combo()
        reset_filters = QPushButton("Сбросить фильтры")
        reset_filters.clicked.connect(self.reset_filters)
        filter_layout = QGridLayout()
        filter_layout.setContentsMargins(16, 12, 16, 14)
        filter_layout.setHorizontalSpacing(10)
        filter_layout.setVerticalSpacing(6)
        for column, (label, widget) in enumerate(
            (
                ("Стол", self.station_filter),
                ("Группа", self.group_filter),
                ("Подгруппа", self.subgroup_filter),
                ("Ранг", self.rank_filter),
                ("Класс", self.class_filter),
            )
        ):
            filter_layout.addWidget(QLabel(label), 0, column)
            filter_layout.addWidget(widget, 1, column)
        for column, (label, widget) in enumerate(
            (
                ("Можно скрафтить", self.craft_filter),
                ("Скупщик", self.trader_filter),
                ("Аукцион", self.auction_filter),
                ("Можно найти", self.find_filter),
                ("Используется", self.used_filter),
            )
        ):
            filter_layout.addWidget(QLabel(label), 2, column)
            filter_layout.addWidget(widget, 3, column)
        filter_layout.addWidget(reset_filters, 3, 5)
        filter_bar = QFrame()
        filter_bar.setObjectName("FilterBar")
        filter_bar.setLayout(filter_layout)

        self.item_form = ItemFormWidget(
            self.builder_service,
            self.item_service,
            self.recipe_service,
            self.reference_service,
            self.catalog_service,
            self.price_service,
        )
        self.item_form.saved.connect(self._after_item_saved)
        self.item_form.deleted.connect(self.reload_catalog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.item_form)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(14, 12, 14, 12)
        content_layout.setSpacing(12)
        content_layout.addWidget(top_bar)
        content_layout.addWidget(filter_bar)
        content_layout.addWidget(scroll, 1)
        content = QFrame()
        content.setObjectName("ContentArea")
        content.setLayout(content_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("MainSplitter")
        splitter.addWidget(sidebar)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 1190])

        central_layout = QHBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(splitter)
        central = QWidget()
        central.setLayout(central_layout)
        self.setCentralWidget(central)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(220)
        self.search_timer.timeout.connect(self.reload_catalog)

    def _connect_filters(self) -> None:
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.group_filter.currentIndexChanged.connect(self._filter_group_changed)
        for widget in (
            self.station_filter,
            self.subgroup_filter,
            self.rank_filter,
            self.class_filter,
            self.craft_filter,
            self.trader_filter,
            self.auction_filter,
            self.find_filter,
            self.used_filter,
        ):
            widget.currentIndexChanged.connect(self.reload_catalog)

    def refresh_filter_values(self) -> None:
        current_group = self.group_filter.currentData()
        self._set_reference_combo(
            self.station_filter,
            [(row.id, row.name) for row in self.reference_service.list_stations()],
            "Все столы",
        )
        self._set_reference_combo(
            self.group_filter,
            [(row.id, row.name) for row in self.reference_service.list_groups()],
            "Все группы",
            current_group,
        )
        self._set_text_combo(self.rank_filter, self.catalog_service.distinct_ranks(), "Все ранги")
        self._set_text_combo(self.class_filter, self.catalog_service.distinct_classes(), "Все классы")
        self._populate_subgroup_filter()

    def reload_catalog(self) -> None:
        selected_id = self.item_form.current_item_id
        summaries = self.catalog_service.list_items(self._current_filters())
        self.tree.blockSignals(True)
        self.tree.clear()
        self._tree_item_by_id.clear()
        groups: dict[int, QTreeWidgetItem] = {}
        subgroups: dict[tuple[int, int | None], QTreeWidgetItem] = {}
        for summary in summaries:
            group_node = groups.get(summary.group_id)
            if group_node is None:
                group_node = QTreeWidgetItem([summary.group_name.upper()])
                group_node.setData(0, Qt.UserRole, None)
                self.tree.addTopLevelItem(group_node)
                groups[summary.group_id] = group_node
            subgroup_key = (summary.group_id, summary.subgroup_id)
            subgroup_node = subgroups.get(subgroup_key)
            if subgroup_node is None:
                subgroup_node = QTreeWidgetItem([summary.subgroup_name or "Без подгруппы"])
                subgroup_node.setData(0, Qt.UserRole, None)
                group_node.addChild(subgroup_node)
                subgroups[subgroup_key] = subgroup_node
            suffix = "  ◆" if summary.craftable else ""
            item_node = QTreeWidgetItem([summary.name + suffix])
            item_node.setData(0, Qt.UserRole, summary.id)
            item_node.setToolTip(
                0,
                f"Крафт: {'да' if summary.craftable else 'нет'} | "
                f"Ингредиент: {'да' if summary.used_in_recipes else 'нет'}",
            )
            subgroup_node.addChild(item_node)
            self._tree_item_by_id[summary.id] = item_node
        self.tree.expandToDepth(1)
        if selected_id in self._tree_item_by_id:
            self.tree.setCurrentItem(self._tree_item_by_id[selected_id])
            self._previous_tree_item = self._tree_item_by_id[selected_id]
        self.tree.blockSignals(False)
        self.result_count.setText(f"Найдено предметов: {len(summaries)}")

    def new_item(self) -> None:
        if not self._confirm_discard():
            return
        group_id = self.group_filter.currentData()
        subgroup_id = self.subgroup_filter.currentData()
        self.tree.clearSelection()
        self._previous_tree_item = None
        self.item_form.new_item(
            group_id=int(group_id) if group_id is not None else None,
            subgroup_id=int(subgroup_id) if subgroup_id is not None else None,
        )

    def add_recipe(self) -> None:
        self.item_form.add_recipe()

    def open_references(self) -> None:
        ReferenceManagerDialog(self.reference_service, self).exec()
        self.item_form.refresh_reference_lookups()
        self.refresh_filter_values()
        self.reload_catalog()

    def reset_filters(self) -> None:
        self.search.clear()
        for widget in (
            self.station_filter,
            self.group_filter,
            self.subgroup_filter,
            self.rank_filter,
            self.class_filter,
            self.craft_filter,
            self.trader_filter,
            self.auction_filter,
            self.find_filter,
            self.used_filter,
        ):
            widget.setCurrentIndex(0)
        self.reload_catalog()

    def _tree_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        if self._restoring_selection or current is None:
            return
        item_id = current.data(0, Qt.UserRole)
        if item_id is None:
            return
        if self.item_form.current_item_id == item_id:
            self._previous_tree_item = current
            return
        if not self._confirm_discard():
            self._restoring_selection = True
            self.tree.setCurrentItem(previous or self._previous_tree_item)
            self._restoring_selection = False
            return
        try:
            self.item_form.load_item(int(item_id))
            self._previous_tree_item = current
        except Exception as exc:
            LOGGER.exception("Не удалось открыть предмет %s", item_id)
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть предмет.\n\n{exc}")

    def _after_item_saved(self, item_id: int) -> None:
        self.refresh_filter_values()
        self.reload_catalog()
        node = self._tree_item_by_id.get(item_id)
        if node is not None:
            self.tree.setCurrentItem(node)

    def _filter_group_changed(self) -> None:
        self._populate_subgroup_filter()
        self.reload_catalog()

    def _populate_subgroup_filter(self) -> None:
        group_id = self.group_filter.currentData()
        rows = self.reference_service.list_subgroups(
            int(group_id) if group_id is not None else None
        )
        self._set_reference_combo(
            self.subgroup_filter,
            [(row.id, f"{row.group.name} / {row.name}") for row in rows],
            "Все подгруппы",
        )

    def _current_filters(self) -> ItemFilters:
        return ItemFilters(
            search=self.search.text(),
            station_id=self.station_filter.currentData(),
            group_id=self.group_filter.currentData(),
            subgroup_id=self.subgroup_filter.currentData(),
            rank=self.rank_filter.currentData(),
            item_class=self.class_filter.currentData(),
            craftable=self.craft_filter.currentData(),
            trader=self.trader_filter.currentData(),
            auction=self.auction_filter.currentData(),
            findable=self.find_filter.currentData(),
            used_in_recipes=self.used_filter.currentData(),
        )

    def _confirm_discard(self) -> bool:
        if not self.item_form.has_unsaved_changes():
            return True
        answer = QMessageBox.question(
            self,
            "Несохранённые изменения",
            "Отменить несохранённые изменения карточки?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Yes

    def _toggle_mode(self) -> None:
        if self.access.is_admin:
            if not self._confirm_discard():
                return
            self.access.mode = AppMode.VIEWER
            if self.item_form.current_item_id is not None:
                self.item_form.load_item(self.item_form.current_item_id)
            self._apply_mode()
            return
        password, accepted = QInputDialog.getText(
            self,
            "Режим администратора",
            "Введите пароль администратора:",
            QLineEdit.Password,
        )
        if not accepted:
            return
        try:
            if not self.settings_service.verify_admin_password(password):
                QMessageBox.warning(self, "Доступ запрещён", "Неверный пароль администратора.")
                return
        except ApplicationError as exc:
            QMessageBox.warning(self, "Настройки", str(exc))
            return
        self.access.mode = AppMode.ADMIN
        self._apply_mode()

    def _apply_mode(self) -> None:
        admin = self.access.is_admin
        self.item_form.set_admin_mode(admin)
        self.add_item_button.setVisible(admin)
        self.add_recipe_button.setVisible(admin)
        self.references_button.setVisible(admin)
        self.mode_button.setText(
            "Администратор · выйти в Viewer" if admin else "Войти как администратор"
        )
        self.top_mode_button.setText(
            "Перейти в Viewer" if admin else "Войти как администратор"
        )
        self.mode_status.setText(
            "ADMIN · РЕДАКТОР" if admin else "VIEWER · ТОЛЬКО ЧТЕНИЕ"
        )
        self.mode_status.setProperty("admin", admin)
        self.mode_status.style().unpolish(self.mode_status)
        self.mode_status.style().polish(self.mode_status)
        self.setWindowTitle(
            "База игровых предметов — Database Builder"
            if admin
            else "База игровых предметов — Database Viewer"
        )
        if self.settings_service.was_created and not admin:
            hint = f"Начальный пароль администратора: {DEFAULT_ADMIN_PASSWORD}. Смените его в настройках."
            self.mode_button.setToolTip(hint)
            self.top_mode_button.setToolTip(hint)
        else:
            self.mode_button.setToolTip("")
            self.top_mode_button.setToolTip("")

    def _change_admin_password(self) -> None:
        current, accepted = QInputDialog.getText(
            self,
            "Смена пароля",
            "Текущий пароль:",
            QLineEdit.Password,
        )
        if not accepted:
            return
        new_password, accepted = QInputDialog.getText(
            self,
            "Смена пароля",
            "Новый пароль (не менее 4 символов):",
            QLineEdit.Password,
        )
        if not accepted:
            return
        confirmation, accepted = QInputDialog.getText(
            self,
            "Смена пароля",
            "Повторите новый пароль:",
            QLineEdit.Password,
        )
        if not accepted:
            return
        if new_password != confirmation:
            QMessageBox.warning(self, "Смена пароля", "Новые пароли не совпадают.")
            return
        try:
            self.settings_service.change_admin_password(current, new_password)
            self.settings_service.was_created = False
            QMessageBox.information(self, "Смена пароля", "Пароль администратора изменён.")
        except ApplicationError as exc:
            QMessageBox.warning(self, "Смена пароля", str(exc))

    def _create_backup(self) -> None:
        try:
            destination = self.backup_service.create_backup()
            QMessageBox.information(
                self,
                "Резервная копия создана",
                f"База успешно скопирована:\n{destination}",
            )
        except ApplicationError as exc:
            QMessageBox.warning(self, "Резервная копия", str(exc))

    def _open_data_folder(self) -> None:
        self.paths.data.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.data))):
            QMessageBox.warning(self, "Папка данных", "Не удалось открыть папку данных.")

    @staticmethod
    def _boolean_combo() -> QComboBox:
        combo = QComboBox()
        combo.addItem("Все", None)
        combo.addItem("Да", True)
        combo.addItem("Нет", False)
        return combo

    @staticmethod
    def _set_reference_combo(
        combo: QComboBox,
        values: list[tuple[int, str]],
        empty_text: str,
        current=None,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(empty_text, None)
        for entity_id, name in values:
            combo.addItem(name, entity_id)
        index = combo.findData(current)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    @staticmethod
    def _set_text_combo(combo: QComboBox, values: list[str], empty_text: str) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(empty_text, None)
        for value in values:
            combo.addItem(value, value)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        combo.blockSignals(False)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._confirm_discard():
            self.database.dispose()
            event.accept()
        else:
            event.ignore()
