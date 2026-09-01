from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from ..providers.base import Metadata


class MetadataPreviewDialog(QDialog):
    def __init__(self, results: list[Metadata], parent=None):
        super().__init__(parent)
        self.results = results
        self.setWindowTitle("Предпросмотр публикации")
        self.resize(760, 620)
        self.network = QNetworkAccessManager(self)
        root = QVBoxLayout(self)
        self.choice = QComboBox()
        for item in results:
            details = " · ".join(part for part in (item.title, item.year, item.source) if part)
            self.choice.addItem(details)
        self.choice.currentIndexChanged.connect(self._load_result)
        root.addWidget(QLabel("Найденная карточка"))
        root.addWidget(self.choice)

        content = QHBoxLayout()
        self.poster = QLabel("Постер не найден")
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setFixedSize(220, 320)
        self.poster.setStyleSheet("border: 1px solid #667; border-radius: 8px;")
        content.addWidget(self.poster)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.year_edit = QLineEdit()
        self.genres_edit = QLineEdit()
        self.cast_edit = QLineEdit()
        self.poster_edit = QLineEdit()
        self.overview_edit = QPlainTextEdit()
        self.overview_edit.setMinimumHeight(170)
        self.source_label = QLabel()
        form.addRow("Название", self.title_edit)
        form.addRow("Год", self.year_edit)
        form.addRow("Жанры", self.genres_edit)
        form.addRow("Актёры", self.cast_edit)
        form.addRow("Описание", self.overview_edit)
        form.addRow("URL постера", self.poster_edit)
        form.addRow("Источник", self.source_label)
        content.addLayout(form, 1)
        root.addLayout(content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Опубликовать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.poster_edit.editingFinished.connect(lambda: self._load_poster(self.poster_edit.text()))
        self._load_result(0)

    def _load_result(self, index: int) -> None:
        if not 0 <= index < len(self.results):
            return
        item = self.results[index]
        self.title_edit.setText(item.title)
        self.year_edit.setText(item.year)
        self.genres_edit.setText(", ".join(item.genres))
        self.cast_edit.setText(", ".join(item.cast))
        self.overview_edit.setPlainText(item.overview)
        self.poster_edit.setText(item.poster_url)
        source = item.source
        if item.source_url:
            source += f" · {item.source_url}"
        self.source_label.setText(source)
        self._load_poster(item.poster_url)

    def _load_poster(self, url: str) -> None:
        self.poster.setText("Загрузка постера…" if url else "Постер не найден")
        self.poster.setPixmap(QPixmap())
        if not url:
            return
        reply = self.network.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(lambda: self._poster_loaded(reply))

    def _poster_loaded(self, reply) -> None:
        data = bytes(reply.readAll())
        reply.deleteLater()
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.poster.setPixmap(pixmap.scaled(self.poster.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.poster.setText("")
        else:
            self.poster.setText("Не удалось загрузить постер")

    def metadata(self) -> Metadata:
        original = self.results[self.choice.currentIndex()]
        return replace(
            original,
            title=self.title_edit.text().strip(),
            year=self.year_edit.text().strip(),
            genres=[item.strip() for item in self.genres_edit.text().split(",") if item.strip()],
            cast=[item.strip() for item in self.cast_edit.text().split(",") if item.strip()],
            overview=self.overview_edit.toPlainText().strip(),
            poster_url=self.poster_edit.text().strip(),
        )
