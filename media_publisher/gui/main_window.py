from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt, QStandardPaths, QThread, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..config.settings import PublisherSettings
from ..media.grouper import group_media
from ..media.scanner import scan_folder
from ..services.publication_service import PublicationService
from ..telegram.bot_api_transport import BotApiTransport, TelegramApiError


PUBLISH_DESTINATIONS = (
    "Фильмы",
    "Мульты",
    "Пожелания",
    "Музыка",
    "Фото",
    "Аниме",
    "Сериалы",
    "Сверхъестественное",
    "Извне",
    "Властелин Колец",
)


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


class PublishWorker(QThread):
    completed = Signal(int)
    failed = Signal(str)

    def __init__(self, token: str, chat_id: str, thread_id: str, target_type: str, target: object):
        super().__init__()
        self.token = token
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.target_type = target_type
        self.target = target

    def run(self) -> None:
        try:
            result = asyncio.run(self._publish())
            self.completed.emit(len(result))
        except Exception as exc:  # Telegram/network errors must return to the UI
            self.failed.emit(str(exc))

    async def _publish(self) -> list[dict]:
        service = PublicationService(BotApiTransport(self.token), self.chat_id, self.thread_id)
        if self.target_type == "media":
            return await service.publish_media(self.target)
        if self.target_type == "season":
            return await service.publish_season(self.target)
        if self.target_type == "show":
            return await service.publish_show(self.target)
        raise ValueError("Неизвестный тип публикации.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Telegram Media Publisher")
        self.resize(980, 680)
        self.settings_path = default_settings_path()
        self.settings = PublisherSettings.load(self.settings_path)
        self._active_destination = self.settings.selected_destination
        self.worker: ScanWorker | None = None
        self.publish_worker: PublishWorker | None = None
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
        self.destination_combo = QComboBox()
        self.destination_combo.addItems(PUBLISH_DESTINATIONS)
        self.destination_combo.currentTextChanged.connect(self.destination_changed)
        form.addRow("Направление", self.destination_combo)
        self.thread_edit = QLineEdit()
        self.thread_edit.setPlaceholderText("ID темы из ссылки на сообщение")
        form.addRow("ID темы", self.thread_edit)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.scan_button = QPushButton("Сканировать")
        self.scan_button.clicked.connect(self.start_scan)
        self.connection_button = QPushButton("Проверить подключение")
        self.connection_button.clicked.connect(self.test_connection)
        self.message_button = QPushButton("Отправить тест")
        self.message_button.clicked.connect(self.send_test)
        self.publish_button = QPushButton("Опубликовать выбранное")
        self.publish_button.clicked.connect(self.publish_selected)
        actions.addWidget(self.scan_button)
        actions.addWidget(self.connection_button)
        actions.addWidget(self.message_button)
        actions.addWidget(self.publish_button)
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
        destination = self.settings.selected_destination
        if destination not in PUBLISH_DESTINATIONS:
            destination = PUBLISH_DESTINATIONS[0]
        self.destination_combo.blockSignals(True)
        self.destination_combo.setCurrentText(destination)
        self.destination_combo.blockSignals(False)
        self._active_destination = destination
        self.thread_edit.setText(self.settings.topic_ids.get(destination, self.settings.thread_id))

    def _save_settings(self) -> None:
        self.settings.folder = self.folder_edit.text().strip()
        self.settings.bot_token = self.token_edit.text().strip()
        self.settings.chat_id = self.chat_edit.text().strip()
        destination = self.destination_combo.currentText()
        topic_id = self.thread_edit.text().strip()
        self.settings.selected_destination = destination
        self.settings.topic_ids[destination] = topic_id
        self.settings.thread_id = topic_id
        self.settings.save(self.settings_path)

    def destination_changed(self, destination: str) -> None:
        if self._active_destination:
            self.settings.topic_ids[self._active_destination] = self.thread_edit.text().strip()
        self._active_destination = destination
        self.settings.selected_destination = destination
        topic_id = self.settings.topic_ids.get(destination, "")
        self.settings.thread_id = topic_id
        self.thread_edit.setText(topic_id)

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
            if show.movies and not show.seasons and len(show.movies) == 1:
                movie = show.movies[0]
                show_item = QTreeWidgetItem([show.title, "Фильм", movie.filename, movie.warning or "найдено"])
                show_item.setData(0, Qt.ItemDataRole.UserRole, ("media", movie))
                self.tree.addTopLevelItem(show_item)
                continue
            show_item = QTreeWidgetItem([show.title, "Сериал" if show.seasons else "Фильмы", "", ""])
            show_item.setData(0, Qt.ItemDataRole.UserRole, ("show", show))
            self.tree.addTopLevelItem(show_item)
            for movie in show.movies:
                movie_item = QTreeWidgetItem(show_item, ["", "Фильм", movie.filename, movie.warning or "найдено"])
                movie_item.setData(0, Qt.ItemDataRole.UserRole, ("media", movie))
            for season in show.seasons:
                season_label = f"Сезон {season.season_number}" if season.season_number else "Сезон не определён"
                season_item = QTreeWidgetItem(["", season_label, "", ", ".join(season.warnings)])
                season_item.setData(0, Qt.ItemDataRole.UserRole, ("season", season))
                show_item.addChild(season_item)
                for media in season.episodes:
                    episode_item = QTreeWidgetItem(season_item, ["", f"Серия {media.episode_number or '—'}", media.filename, "найдено"])
                    episode_item.setData(0, Qt.ItemDataRole.UserRole, ("media", media))
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
            if not self.settings.thread_id:
                QMessageBox.warning(self, "Telegram", "Укажите ID выбранной темы. Отправка в основную тему отключена.")
                return
            destination = self.settings.selected_destination
            self._run_async(
                transport.send_message(f"Тестовое сообщение Media Publisher · {destination}", self.settings.chat_id, self.settings.thread_id),
                f"Сообщение отправлено в тему «{destination}».",
            )

    def publish_selected(self) -> None:
        self._save_settings()
        if not self.settings.bot_token or not self.settings.chat_id:
            QMessageBox.warning(self, "Публикация", "Заполните токен бота и Chat ID.")
            return
        if not self.settings.thread_id:
            QMessageBox.warning(self, "Публикация", "Укажите ID выбранной темы. Отправка в основную тему отключена.")
            return
        item = self.tree.currentItem()
        target_data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not target_data:
            QMessageBox.warning(self, "Публикация", "Выберите фильм, сезон, серию или весь сериал в таблице.")
            return
        target_type, target = target_data
        label = item.text(0) or item.text(1) or item.text(2)
        answer = QMessageBox.question(
            self,
            "Подтверждение публикации",
            f"Опубликовать «{label}» в тему «{self.settings.selected_destination}»\n"
            f"Chat ID: {self.settings.chat_id}\nID темы: {self.settings.thread_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.publish_button.setEnabled(False)
        self.progress.show()
        self.status.setText(f"Публикация в тему «{self.settings.selected_destination}»…")
        self.publish_worker = PublishWorker(
            self.settings.bot_token,
            self.settings.chat_id,
            self.settings.thread_id,
            target_type,
            target,
        )
        self.publish_worker.completed.connect(self.publish_completed)
        self.publish_worker.failed.connect(self.publish_failed)
        self.publish_worker.finished.connect(lambda: (self.publish_button.setEnabled(True), self.progress.hide()))
        self.publish_worker.start()

    def publish_completed(self, count: int) -> None:
        self.status.setText(f"Публикация завершена: отправлено сообщений — {count}.")
        QMessageBox.information(self, "Публикация", "Материал успешно опубликован.")

    def publish_failed(self, message: str) -> None:
        self.status.setText("Ошибка публикации")
        QMessageBox.critical(self, "Публикация", message)


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
