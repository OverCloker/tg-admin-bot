from pathlib import Path

from media_publisher.config.settings import PublisherSettings
from media_publisher.media.grouper import group_media
from media_publisher.media.scanner import scan_folder
from media_publisher.models import MediaFileInfo, SeasonGroup, ShowGroup
from media_publisher.parsers.filename_parser import parse_filename


def test_filename_parser_extracts_series_data(tmp_path: Path):
    path = tmp_path / "The.Show.S02E03.1080p.WEB-DL.mkv"
    path.touch()
    item = parse_filename(path)
    assert item.title == "The Show"
    assert item.season_number == 2
    assert item.episode_number == 3
    assert item.quality == "1080p"


def test_scan_and_group_reports_missing_episode(tmp_path: Path):
    (tmp_path / "Demo S01E01.mp4").touch()
    (tmp_path / "Demo S01E03.mp4").touch()
    groups = group_media(scan_folder(tmp_path))
    assert groups[0].title == "Demo"
    assert groups[0].seasons[0].missing_episodes == [2]


def test_settings_round_trip_uses_utf8(tmp_path: Path):
    path = tmp_path / "settings.json"
    settings = PublisherSettings(folder="D:/Медиа", chat_id="-1001")
    settings.save(path)
    loaded = PublisherSettings.load(path)
    assert loaded.folder == "D:/Медиа"
    assert loaded.chat_id == "-1001"


def test_main_window_renders_model_tree(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from media_publisher.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    media = MediaFileInfo(
        path=tmp_path / "Demo S01E02.mp4",
        filename="Demo S01E02.mp4",
        title="Demo",
        season_number=1,
        episode_number=2,
    )
    window = MainWindow()
    window.show_groups([ShowGroup("Demo", [SeasonGroup("Demo", 1, [media])])])

    show_item = window.tree.topLevelItem(0)
    season_item = show_item.child(0)
    episode_item = season_item.child(0)
    assert season_item.text(1) == "Сезон 1"
    assert episode_item.text(1) == "Серия 2"
    assert episode_item.text(2) == "Demo S01E02.mp4"
    window.close()
    del app
