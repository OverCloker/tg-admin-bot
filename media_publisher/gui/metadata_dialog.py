from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..models import MediaFileInfo, SeasonGroup
from ..providers.base import Metadata
from ..services.template_renderer import TemplateRenderer


class MetadataPreviewDialog(QDialog):
    RetrySearch = 2

    def __init__(self, results: list[Metadata], target: MediaFileInfo | SeasonGroup | None = None, parent=None):
        super().__init__(parent)
        self.results = results
        self.target = target
        self.setWindowTitle("Предпросмотр публикации")
        self.resize(900, 780)
        self.network = QNetworkAccessManager(self)
        root = QVBoxLayout(self)
        self.choice = QComboBox()
        for item in results:
            details = " · ".join(part for part in (item.title, item.original_title, item.season_year or item.year, item.source) if part)
            self.choice.addItem(details)
        self.choice.currentIndexChanged.connect(self._load_result)
        root.addWidget(QLabel("Найденная карточка — выберите правильный вариант:"))
        root.addWidget(self.choice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        content = QHBoxLayout(body)
        left = QVBoxLayout()
        self.poster = QLabel("Постер не найден")
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setFixedSize(260, 380)
        self.poster.setStyleSheet("border: 1px solid #667; border-radius: 8px;")
        left.addWidget(self.poster)
        poster_button = QPushButton("Выбрать другой постер")
        poster_button.clicked.connect(self.choose_poster)
        left.addWidget(poster_button)
        self.poster_options = QComboBox()
        self.poster_options.currentIndexChanged.connect(self._poster_option_changed)
        left.addWidget(self.poster_options)
        left.addStretch()
        content.addLayout(left)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.original_title_edit = QLineEdit()
        self.year_edit = QLineEdit()
        self.season_year_edit = QLineEdit()
        self.genres_edit = QLineEdit()
        self.cast_edit = QPlainTextEdit()
        self.cast_edit.setMaximumHeight(75)
        self.imdb_edit = QLineEdit()
        self.imdb_votes_edit = QLineEdit()
        self.kinopoisk_edit = QLineEdit()
        self.kinopoisk_votes_edit = QLineEdit()
        self.dub_edit = QLineEdit()
        self.season_edit = QLineEdit()
        self.episodes_edit = QLineEdit()
        self.overview_edit = QPlainTextEdit()
        self.season_overview_edit = QPlainTextEdit()
        self.poster_edit = QLineEdit()
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        for label, widget in (
            ("Название", self.title_edit), ("Оригинальное название", self.original_title_edit),
            ("Год", self.year_edit), ("Год сезона", self.season_year_edit),
            ("Жанры", self.genres_edit), ("Актёры", self.cast_edit),
            ("IMDb", self.imdb_edit), ("Голоса IMDb", self.imdb_votes_edit),
            ("Кинопоиск", self.kinopoisk_edit), ("Голоса Кинопоиск", self.kinopoisk_votes_edit),
            ("Дубляж", self.dub_edit), ("Сезон", self.season_edit),
            ("Серии", self.episodes_edit), ("Общее описание", self.overview_edit),
            ("Описание сезона", self.season_overview_edit), ("URL / файл постера", self.poster_edit),
            ("Источник", self.source_label),
        ):
            form.addRow(label, widget)
        content.addLayout(form, 1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        root.addWidget(QLabel("Так будет выглядеть подпись карточки в Telegram:"))
        self.ready_preview = QPlainTextEdit()
        self.ready_preview.setReadOnly(True)
        self.ready_preview.setMaximumHeight(180)
        root.addWidget(self.ready_preview)
        self.next_message = QLabel()
        self.next_message.setWordWrap(True)
        root.addWidget(self.next_message)

        buttons = QHBoxLayout()
        retry = QPushButton("Повторить поиск")
        retry.clicked.connect(lambda: self.done(self.RetrySearch))
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        publish = QPushButton("Опубликовать")
        publish.clicked.connect(self._accept_validated)
        buttons.addWidget(retry)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(publish)
        root.addLayout(buttons)
        self.poster_edit.editingFinished.connect(lambda: self._load_poster(self.poster_edit.text()))
        for widget in (self.title_edit, self.year_edit, self.genres_edit, self.dub_edit, self.season_edit, self.episodes_edit):
            widget.textChanged.connect(self._refresh_ready_preview)
        self.overview_edit.textChanged.connect(self._refresh_ready_preview)
        self.season_overview_edit.textChanged.connect(self._refresh_ready_preview)
        self._load_result(0)

    def _load_result(self, index: int) -> None:
        if not 0 <= index < len(self.results):
            return
        item = self.results[index]
        values = {
            self.title_edit: item.title, self.original_title_edit: item.original_title,
            self.year_edit: item.year, self.season_year_edit: item.season_year,
            self.genres_edit: ", ".join(item.genres), self.imdb_edit: item.imdb_rating,
            self.imdb_votes_edit: item.imdb_votes, self.kinopoisk_edit: item.kinopoisk_rating,
            self.kinopoisk_votes_edit: item.kinopoisk_votes, self.dub_edit: item.dub,
            self.season_edit: str(item.season_number or ""),
            self.episodes_edit: ", ".join(map(str, item.episode_numbers)),
            self.poster_edit: item.poster_path or item.poster_url or item.season_poster_url,
        }
        for widget, value in values.items():
            widget.setText(value)
        self.cast_edit.setPlainText(", ".join(item.cast))
        self.overview_edit.setPlainText(item.overview)
        self.season_overview_edit.setPlainText(item.season_overview)
        self.source_label.setText(" · ".join(part for part in (item.source, item.source_url) if part))
        self.poster_options.blockSignals(True)
        self.poster_options.clear()
        poster_choices = []
        for source in (item.poster_path, item.poster_url, item.season_poster_url, *item.poster_options):
            if source and source not in poster_choices:
                poster_choices.append(source)
        for number, source in enumerate(poster_choices, 1):
            self.poster_options.addItem(f"Вариант постера {number}", source)
        self.poster_options.setVisible(len(poster_choices) > 1)
        self.poster_options.blockSignals(False)
        self._load_poster(self.poster_edit.text())
        self._refresh_ready_preview()

    def choose_poster(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Выберите постер", "", "Изображения (*.jpg *.jpeg *.png *.webp)")
        if selected:
            self.poster_edit.setText(selected)
            self._load_poster(selected)

    def _poster_option_changed(self, index: int) -> None:
        source = self.poster_options.itemData(index)
        if source:
            self.poster_edit.setText(source)
            self._load_poster(source)

    def _load_poster(self, source: str) -> None:
        self.poster.setPixmap(QPixmap())
        path = Path(source)
        if path.is_file():
            self._set_pixmap(QPixmap(str(path)))
            return
        self.poster.setText("Загрузка постера…" if source else "Постер не найден")
        if source.startswith(("http://", "https://")):
            reply = self.network.get(QNetworkRequest(QUrl(source)))
            reply.finished.connect(lambda: self._poster_loaded(reply))

    def _poster_loaded(self, reply) -> None:
        data = bytes(reply.readAll())
        reply.deleteLater()
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self._set_pixmap(pixmap)
        else:
            self.poster.setText("Не удалось загрузить постер")

    def _set_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.poster.setText("Не удалось открыть постер")
            return
        self.poster.setPixmap(pixmap.scaled(self.poster.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.poster.setText("")

    def _refresh_ready_preview(self) -> None:
        if not hasattr(self, "ready_preview"):
            return
        metadata = self.metadata()
        renderer = TemplateRenderer()
        if isinstance(self.target, SeasonGroup):
            text = renderer.season(metadata, self.target)
            numbers = [item.episode_number for item in self.target.episodes if item.episode_number is not None]
            first, last = (min(numbers), max(numbers)) if numbers else (1, len(self.target.episodes))
            next_text = renderer.media_group(self.target, first, last) + f"\n\n{len(self.target.episodes)} видео"
        else:
            dub = self.target.dub if isinstance(self.target, MediaFileInfo) else ""
            text = renderer.movie(metadata, dub or "")
            next_text = "Следующее сообщение: видеофайл"
        self.ready_preview.setPlainText(text)
        self.next_message.setText(next_text)

    def _accept_validated(self) -> None:
        if not self.title_edit.text().strip():
            self.title_edit.setFocus()
            return
        if not self.poster_edit.text().strip():
            self.poster.setText("Выберите постер перед публикацией")
            return
        self.accept()

    def metadata(self) -> Metadata:
        original = self.results[max(0, self.choice.currentIndex())]
        poster_source = self.poster_edit.text().strip()
        return replace(
            original,
            title=self.title_edit.text().strip(), original_title=self.original_title_edit.text().strip(),
            year=self.year_edit.text().strip(), season_year=self.season_year_edit.text().strip(),
            genres=[value.strip() for value in self.genres_edit.text().split(",") if value.strip()],
            cast=[value.strip() for value in self.cast_edit.toPlainText().split(",") if value.strip()],
            imdb_rating=self.imdb_edit.text().strip(), imdb_votes=self.imdb_votes_edit.text().strip(),
            kinopoisk_rating=self.kinopoisk_edit.text().strip(), kinopoisk_votes=self.kinopoisk_votes_edit.text().strip(),
            dub=self.dub_edit.text().strip(), season_number=int(self.season_edit.text()) if self.season_edit.text().isdigit() else None,
            episode_numbers=[int(value.strip()) for value in self.episodes_edit.text().split(",") if value.strip().isdigit()],
            overview=self.overview_edit.toPlainText().strip(), season_overview=self.season_overview_edit.toPlainText().strip(),
            poster_path=poster_source if Path(poster_source).is_file() else "",
            poster_url=poster_source if poster_source.startswith(("http://", "https://")) else original.poster_url,
        )
