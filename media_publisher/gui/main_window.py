from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QThread, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..config.settings import PublisherSettings
from ..media.grouper import group_media
from ..media.scanner import scan_folder
from ..telegram.bot_api_transport import BotApiTransport, TelegramApiError


def default_settings_path() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    return Path(location) / "settings.json"


class ScanWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, folder: str):
        super().__init__()
        self.folder = folder

    def run(self) -> None:
        try:
            files = scan_folder(self.folder)
            self.completed.emit(group_media(files))
        except Exception as exc:  # keep filesystem errors inside the GUI
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Telegram Media Publisher")
        self.resize(980, 680)
        self.settings_path = default_settings_path()
        self.settings = PublisherSettings.load(self.settings_path)
        self.worker: ScanWorker | None = None
        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        form = QFormLayout()
        self.folder_edit = QLineEdit()
        browse = QPushButton("Выбрать папку")
        browse.clicked.connect(self.choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        form.addRow("Папка с медиа", folder_row)
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("Токен хранится только локально")
        form.addRow("Токен бота", self.token_edit)
        self.chat_edit = QLineEdit()
        self.chat_edit.setPlaceholderText("например, -1001234567890")
        form.addRow("Chat ID", self.chat_edit)
        self.thread_edit = QLineEdit()
        form.addRow("Тема (необязательно)", self.thread_edit)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.scan_button = QPushButton("Сканировать")
        self.scan_button.clicked.connect(self.start_scan)
        self.connection_button = QPushButton("Проверить подключение")
        self.connection_button.clicked.connect(self.test_connection)
        self.message_button = QPushButton("Отправить тест")
        self.message_button.clicked.connect(self.send_test)
        actions.addWidget(self.scan_button)
        actions.addWidget(self.connection_button)
        actions.addWidget(self.message_button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("Выберите папку и запустите сканирование.")
        layout.addWidget(self.status)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Релиз", "Сезон / серия", "Файл", "Статус"])
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, 1)
        self.setCentralWidget(root)

    def _load_settings(self) -> None:
        self.folder_edit.setText(self.settings.folder)
        self.token_edit.setText(self.settings.bot_token)
        self.chat_edit.setText(self.settings.chat_id)
        self.thread_edit.setText(self.settings.thread_id)

    def _save_settings(self) -> None:
        self.settings.folder = self.folder_edit.text().strip()
        self.settings.bot_token = self.token_edit.text().strip()
        self.settings.chat_id = self.chat_edit.text().strip()
        self.settings.thread_id = self.thread_edit.text().strip()
        self.settings.save(self.settings_path)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Выберите папку с медиа", self.folder_edit.text())
        if selected:
            self.folder_edit.setText(selected)

    def start_scan(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Сканирование", "Укажите существующую папку.")
            return
        self._save_settings()
        self.scan_button.setEnabled(False)
        self.progress.show()
        self.status.setText("Сканирование…")
        self.worker = ScanWorker(folder)
        self.worker.completed.connect(self.show_groups)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(lambda: (self.scan_button.setEnabled(True), self.progress.hide()))
        self.worker.start()

    def show_groups(self, groups: list) -> None:
        self.tree.clear()
        for show in groups:
            show_item = QTreeWidgetItem([show.title, "", "", ""])
            self.tree.addTopLevelItem(show_item)
            for season in show.seasons:
                season_item = QTreeWidgetItem(["", f"Сезон {season.season_number}", "", ", ".join(season.warnings)])
                show_item.addChild(season_item)
                for media in season.episodes:
                    QTreeWidgetItem(season_item, ["", f"Серия {media.episode or '—'}", media.path.name, "найдено"])
            show_item.setExpanded(True)
        self.status.setText(f"Найдено релизов: {len(groups)}")

    def scan_failed(self, message: str) -> None:
        self.status.setText("Ошибка сканирования")
        QMessageBox.critical(self, "Сканирование", message)

    def _transport(self) -> BotApiTransport | None:
        self._save_settings()
        if not self.settings.bot_token or not self.settings.chat_id:
            QMessageBox.warning(self, "Telegram", "Заполните токен и Chat ID.")
            return None
        return BotApiTransport(self.settings.bot_token)

    def _run_async(self, operation, success: str) -> None:
        try:
            asyncio.run(operation)
            QMessageBox.information(self, "Telegram", success)
        except (TelegramApiError, OSError) as exc:
            QMessageBox.critical(self, "Telegram", str(exc))

    def test_connection(self) -> None:
        transport = self._transport()
        if transport:
            self._run_async(transport.test_connection(), "Подключение успешно.")

    def send_test(self) -> None:
        transport = self._transport()
        if transport:
            self._run_async(transport.send_message("Тестовое сообщение Media Publisher", self.settings.chat_id, self.settings.thread_id), "Сообщение отправлено.")


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(32, 36, 43))
    palette.setColor(QPalette.WindowText, QColor(235, 238, 242))
    palette.setColor(QPalette.Base, QColor(24, 27, 32))
    palette.setColor(QPalette.AlternateBase, QColor(42, 47, 55))
    palette.setColor(QPalette.Text, QColor(235, 238, 242))
    palette.setColor(QPalette.Button, QColor(55, 63, 74))
    palette.setColor(QPalette.ButtonText, QColor(235, 238, 242))
    app.setPalette(palette)
