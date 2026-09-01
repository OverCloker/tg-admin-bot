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
from ..database.repository import PublisherDatabase
from ..media.grouper import group_media
from ..media.scanner import scan_folder
from ..providers.base import Metadata
from ..providers.omdb_provider import OmdbProvider
from ..providers.rezka_provider import RezkaProvider
from ..providers.tmdb_provider import TmdbProvider
from ..services.metadata_service import MetadataService
from ..services.poster_cache import PosterCache
from ..services.publication_service import PublicationService
from ..telegram.bot_api_transport import BotApiTransport, TelegramApiError
from .metadata_dialog import MetadataPreviewDialog


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


def default_database_path() -> Path:
    return default_settings_path().with_name("publisher.sqlite3")


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

    def __init__(self, token: str, chat_id: str, thread_id: str, target_type: str, target: object, metadata: Metadata):
        super().__init__()
        self.token = token
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.target_type = target_type
        self.target = target
        self.metadata = metadata

    def run(self) -> None:
        try:
            result = asyncio.run(self._publish())
            self.completed.emit(len(result))
        except Exception as exc:  # Telegram/network errors must return to the UI
            self.failed.emit(str(exc))

    async def _publish(self) -> list[dict]:
        database = PublisherDatabase(default_database_path())
        try:
            if not self.metadata.poster_path:
                try:
                    await PosterCache(default_settings_path().with_name("posters")).cache(self.metadata)
                except Exception as exc:
                    raise ValueError(f"Не удалось загрузить постер для Telegram: {exc}") from exc
            if self.target_type == "media":
                paths = [self.target.path]
            elif self.target_type == "season":
                paths = [item.path for item in self.target.episodes]
            elif self.target_type == "show":
                paths = [item.path for item in self.target.movies]
                paths += [item.path for season in self.target.seasons for item in season.episodes]
            else:
                raise ValueError("Неизвестный тип публикации.")
            operation_key = PublicationService.make_operation_key(self.chat_id, self.thread_id, paths, self.metadata)
            service = PublicationService(BotApiTransport(self.token), self.chat_id, self.thread_id, database, operation_key)
            if self.target_type == "media":
                return await service.publish_media(self.target, metadata=self.metadata)
            if self.target_type == "season":
                return await service.publish_season(self.target, metadata=self.metadata)
            return await service.publish_show(self.target, metadata=self.metadata)
        finally:
            database.close()


class MetadataWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, title: str, season: int | None, settings: PublisherSettings, dub: str = "", episodes: list[int] | None = None, force: bool = False):
        super().__init__()
        self.title = title
        self.season = season
        self.settings = settings
        self.dub = dub
        self.episodes = episodes or []
        self.force = force

    def run(self) -> None:
        database = None
        try:
            database = PublisherDatabase(default_database_path())
            providers = [RezkaProvider(self.settings.rezka_domain)]
            if self.settings.tmdb_api_key:
                providers.append(TmdbProvider(self.settings.tmdb_api_key))
            if self.settings.omdb_api_key:
                providers.append(OmdbProvider(self.settings.omdb_api_key))
            results = asyncio.run(MetadataService(database, providers).find(self.title, self.season, force=self.force))
            poster_cache = PosterCache(default_settings_path().with_name("posters"))
            for item in results:
                item.dub = item.dub or self.dub
                item.episode_numbers = item.episode_numbers or self.episodes
                try:
                    asyncio.run(poster_cache.cache(item))
                except Exception:
                    pass
            self.completed.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if database:
                database.close()


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
        self.metadata_worker: MetadataWorker | None = None
        self.pending_publication: tuple[str, object] | None = None
        self._metadata_target: tuple[str, object] | None = None
        self._metadata_results: list[Metadata] = []
        self._lookup_for_publish = False
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
        self.rezka_edit = QLineEdit()
        self.rezka_edit.setPlaceholderText("необязательно: своё рабочее зеркало")
        form.addRow("Домен Rezka", self.rezka_edit)
        self.tmdb_edit = QLineEdit()
        self.tmdb_edit.setEchoMode(QLineEdit.Password)
        self.tmdb_edit.setPlaceholderText("необязательно, для данных конкретного сезона")
        form.addRow("TMDB API key", self.tmdb_edit)
        self.omdb_edit = QLineEdit()
        self.omdb_edit.setEchoMode(QLineEdit.Password)
        self.omdb_edit.setPlaceholderText("необязательно, для IMDb и голосов")
        form.addRow("OMDb API key", self.omdb_edit)
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
        self.preview_button = QPushButton("Предпросмотр")
        self.preview_button.clicked.connect(self.preview_selected)
        actions.addWidget(self.scan_button)
        actions.addWidget(self.connection_button)
        actions.addWidget(self.message_button)
        actions.addWidget(self.preview_button)
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
        self.tree.currentItemChanged.connect(self.selection_changed)
        layout.addWidget(self.tree, 1)
        self.metadata_summary = QLabel("Карточка появится автоматически после выбора фильма или сезона.")
        self.metadata_summary.setWordWrap(True)
        self.metadata_summary.setStyleSheet("padding: 8px; border: 1px solid #556; border-radius: 6px;")
        layout.addWidget(self.metadata_summary)
        self.setCentralWidget(root)

    def _load_settings(self) -> None:
        self.folder_edit.setText(self.settings.folder)
        self.token_edit.setText(self.settings.bot_token)
        self.chat_edit.setText(self.settings.chat_id)
        self.rezka_edit.setText(self.settings.rezka_domain)
        self.tmdb_edit.setText(self.settings.tmdb_api_key)
        self.omdb_edit.setText(self.settings.omdb_api_key)
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
        self.settings.rezka_domain = self.rezka_edit.text().strip()
        self.settings.tmdb_api_key = self.tmdb_edit.text().strip()
        self.settings.omdb_api_key = self.omdb_edit.text().strip()
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
        if self.tree.topLevelItemCount():
            first = self.tree.topLevelItem(0)
            self.tree.setCurrentItem(first.child(0) if first.childCount() else first)

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
        target_data = self._selected_target()
        if not target_data:
            QMessageBox.warning(self, "Публикация", "Выберите фильм, сезон, серию или весь сериал в таблице.")
            return
        self.pending_publication = target_data
        self._lookup_for_publish = True
        if self._metadata_target == target_data and self._metadata_results:
            self._open_preview(self._metadata_results)
        else:
            self._start_metadata_lookup(target_data, for_publish=True)

    def _selected_target(self) -> tuple[str, object] | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    @staticmethod
    def _target_context(target: object) -> tuple[str, int | None, str, list[int]]:
        title = getattr(target, "title", "")
        season = getattr(target, "season_number", None)
        dub = getattr(target, "dub", "") or ""
        episodes = []
        if hasattr(target, "episodes"):
            episodes = [item.episode_number for item in target.episodes if item.episode_number is not None]
        elif getattr(target, "episode_number", None) is not None:
            episodes = [target.episode_number]
        return title, season, dub, episodes

    def selection_changed(self, current, previous=None) -> None:
        target_data = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if not target_data:
            return
        target_type, target = target_data
        if target_type == "show" and len(getattr(target, "seasons", [])) + len(getattr(target, "movies", [])) != 1:
            self.metadata_summary.setText("Выберите конкретный сезон или фильм.")
            return
        self._start_metadata_lookup(target_data, for_publish=False)

    def preview_selected(self) -> None:
        target_data = self._selected_target()
        if not target_data:
            QMessageBox.warning(self, "Предпросмотр", "Выберите фильм или сезон.")
            return
        self.pending_publication = target_data
        self._lookup_for_publish = False
        if self._metadata_target == target_data and self._metadata_results:
            self._open_preview(self._metadata_results)
        else:
            self._start_metadata_lookup(target_data, for_publish=False)

    def _start_metadata_lookup(self, target_data: tuple[str, object], *, for_publish: bool, force: bool = False) -> None:
        if self.metadata_worker and self.metadata_worker.isRunning():
            self.metadata_summary.setText("Дождитесь завершения текущего поиска метаданных.")
            return
        self._save_settings()
        self._metadata_target = target_data
        self._metadata_results = []
        self._lookup_for_publish = for_publish
        target_type, target = target_data
        title, season, dub, episodes = self._target_context(target)
        self.progress.show()
        self.status.setText(f"Ищу точную карточку: {title}" + (f", сезон {season}" if season else "") + "…")
        self.metadata_worker = MetadataWorker(title, season, self.settings, dub, episodes, force)
        self.metadata_worker.completed.connect(self.metadata_ready)
        self.metadata_worker.failed.connect(self.metadata_failed)
        self.metadata_worker.start()

    def metadata_ready(self, results: list[Metadata]) -> None:
        self.progress.hide()
        if not results:
            self.publish_button.setEnabled(True)
            self.status.setText("Метаданные не найдены")
            QMessageBox.warning(
                self,
                "Метаданные",
                "Rezka и резервные источники не вернули карточку. Проверьте домен Rezka или название — публикация остановлена.",
            )
            return
        self._metadata_results = results
        first = results[0]
        season_text = f" · сезон {first.season_number}" if first.season_number else ""
        year = first.season_year or first.year
        self.metadata_summary.setText(
            f"Найдена карточка: {first.title}{season_text}" + (f" · {year}" if year else "")
            + f"\nИсточник: {first.source}. Вариантов: {len(results)}. "
            + "Откройте предпросмотр, чтобы проверить постер и данные."
        )
        self.status.setText("Метаданные загружены. Проверьте готовую карточку перед публикацией.")
        if self._lookup_for_publish:
            self._open_preview(results)

    def _open_preview(self, results: list[Metadata]) -> None:
        if not self._metadata_target:
            return
        target_type, target = self._metadata_target
        dialog = MetadataPreviewDialog(results, target, self)
        result = dialog.exec()
        if result == MetadataPreviewDialog.RetrySearch:
            self._start_metadata_lookup(self._metadata_target, for_publish=self._lookup_for_publish, force=True)
            return
        if not result:
            self.publish_button.setEnabled(True)
            self.status.setText("Предпросмотр закрыт без публикации")
            return
        metadata = dialog.metadata()
        title, season, _, _ = self._target_context(target)
        database = PublisherDatabase(default_database_path())
        try:
            MetadataService(database).save_selection(title, season, metadata)
        finally:
            database.close()
        self._metadata_results = [metadata]
        self.start_publication(metadata)

    def metadata_failed(self, message: str) -> None:
        self.progress.hide()
        self.publish_button.setEnabled(True)
        self.status.setText("Ошибка поиска метаданных")
        QMessageBox.critical(self, "Метаданные", message)

    def start_publication(self, metadata: Metadata) -> None:
        if not self.pending_publication:
            self.publish_button.setEnabled(True)
            return
        target_type, target = self.pending_publication
        self.progress.show()
        self.status.setText(f"Публикация в тему «{self.settings.selected_destination}»…")
        self.publish_worker = PublishWorker(
            self.settings.bot_token,
            self.settings.chat_id,
            self.settings.thread_id,
            target_type,
            target,
            metadata,
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
