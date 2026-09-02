from __future__ import annotations

import logging
import sys
from types import TracebackType

from app.database.migrations import upgrade_database
from app.database.seed import seed_acquisition_methods
from app.database.session import Database
from app.logging_config import configure_logging, flush_logging_handlers
from app.paths import PATHS, AppPaths


LOGGER = logging.getLogger(__name__)


def initialize_database() -> Database:
    PATHS.ensure_directories()
    upgrade_database(PATHS.database)
    database = Database(PATHS.database)
    seed_acquisition_methods(database.session_factory)
    return database


def run() -> int:
    configure_logging(PATHS)
    LOGGER.info("Запуск приложения; журнал: %s", PATHS.logs / "app.log")
    try:
        database = initialize_database()
        from PySide6.QtWidgets import QApplication, QMessageBox

        from app.ui.main_window import MainWindow

        application = QApplication(sys.argv)
        application.setApplicationName("База игровых предметов")
        _install_exception_hook(PATHS)
        window = MainWindow(database=database, paths=PATHS)
        window.show()
        return application.exec()
    except Exception as exc:  # pragma: no cover - last-resort desktop guard
        LOGGER.exception("Не удалось запустить приложение")
        flush_logging_handlers()
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            application = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "Ошибка запуска",
                f"Приложение не удалось запустить. Подробности записаны в logs/app.log.\n\n{exc}",
            )
        except Exception:
            print(f"Ошибка запуска: {exc}", file=sys.stderr)
        return 1


def _install_exception_hook(paths: AppPaths = PATHS) -> None:
    original_hook = sys.excepthook

    def handle_exception(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        if issubclass(exception_type, KeyboardInterrupt):
            original_hook(exception_type, exception, traceback)
            return
        LOGGER.critical(
            "Необработанная ошибка интерфейса",
            exc_info=(exception_type, exception, traceback),
        )
        flush_logging_handlers()
        error_text = f"{exception_type.__name__}: {exception}"
        try:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                None,
                "Непредвиденная ошибка",
                "Операция завершилась ошибкой. Данные не были сохранены частично.\n\n"
                f"{error_text}\n\n"
                f"Подробности записаны в {paths.logs / 'app.log'}.",
            )
        except Exception:
            original_hook(exception_type, exception, traceback)

    sys.excepthook = handle_exception
