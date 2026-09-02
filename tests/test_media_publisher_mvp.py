import asyncio
from pathlib import Path

from media_publisher.config.settings import PublisherSettings
from media_publisher.database.repository import PublisherDatabase
from media_publisher.media.grouper import group_media
from media_publisher.media.scanner import scan_folder
from media_publisher.models import MediaFileInfo, SeasonGroup, ShowGroup
from media_publisher.parsers.filename_parser import parse_filename
from media_publisher.providers.base import Metadata, MetadataProvider
from media_publisher.providers.rezka_provider import RezkaProvider, _solve_anubis_pow
from media_publisher.services.metadata_service import MetadataService
from media_publisher.services.publication_service import PublicationService
from media_publisher.services.template_renderer import TemplateRenderer
from media_publisher.telegram.base_transport import TelegramTransport
from media_publisher.telegram.bot_api_transport import BotApiTransport, TelegramApiError


class RecordingTransport(TelegramTransport):
    def __init__(self):
        self.calls = []

    async def test_connection(self):
        return {}

    async def send_message(self, text, chat_id, thread_id=""):
        self.calls.append(("message", text, chat_id, thread_id))
        return {"message_id": 1}

    async def send_photo(self, photo, caption, chat_id, thread_id=""):
        self.calls.append(("photo", photo, caption, chat_id, thread_id))
        return {"message_id": 1}

    async def send_video(self, video, caption, chat_id, thread_id=""):
        self.calls.append(("video", video, caption, chat_id, thread_id))
        return {"message_id": 1}

    async def send_document(self, document, caption, chat_id, thread_id=""):
        self.calls.append(("document", document, caption, chat_id, thread_id))
        return {"message_id": 1}

    async def send_media_group(self, files, caption, chat_id, thread_id=""):
        self.calls.append(("group", files, caption, chat_id, thread_id))
        return [{"message_id": index + 1} for index in range(len(files))]


class StaticMetadataProvider(MetadataProvider):
    name = "static"

    async def search(self, title, season=None):
        return [Metadata(title=title, year="2025"), Metadata(title=title + " 2", year="2026")]


def test_filename_parser_extracts_series_data(tmp_path: Path):
    path = tmp_path / "The.Show.S02E03.1080p.WEB-DL.mkv"
    path.touch()
    item = parse_filename(path)
    assert item.title == "The Show"
    assert item.season_number == 2
    assert item.episode_number == 3
    assert item.quality == "1080p"
    assert item.media_type == "series"


def test_filename_parser_handles_exported_rezka_series_name(tmp_path: Path):
    path = tmp_path / "Миротворец - все серии 1 сезона в озвучке HDrezka Studio s-Сезон 2 ep-Серия 8 [HDrezka Studio (18+)].mp4"
    path.touch()
    item = parse_filename(path)
    assert item.title == "Миротворец"
    assert item.season_number == 2
    assert item.episode_number == 8
    assert item.dub == "HDrezka Studio"
    assert item.age_rating == "18+"


def test_filename_parser_treats_file_without_episode_markers_as_movie(tmp_path: Path):
    path = tmp_path / "Властелины вселенной s- ep- [Лостфильм].mp4"
    path.touch()
    item = parse_filename(path)
    assert item.media_type == "movie"
    assert item.season_number is None
    assert item.episode_number is None
    assert item.warning is None
    assert item.title == "Властелины вселенной"


def test_filename_parser_extracts_movie_dub_before_trailing_quality(tmp_path: Path):
    path = tmp_path / "Миньоны и монстры s- ep- [Украинский дубляж] [1080p].mp4"
    path.touch()
    item = parse_filename(path)
    assert item.title == "Миньоны и монстры"
    assert item.dub == "Украинский дубляж"


def test_filename_parser_extracts_named_voice_phrase(tmp_path: Path):
    path = tmp_path / "Зверополис 2 в озвучке Украинский дубляж.mp4"
    path.touch()
    item = parse_filename(path)
    assert item.title == "Зверополис 2"
    assert item.dub == "Украинский дубляж"


def test_filename_parser_extracts_unbracketed_dub_suffix(tmp_path: Path):
    path = tmp_path / "Зверополис 2 - Дубляж официальный.mp4"
    path.touch()
    item = parse_filename(path)
    assert item.title == "Зверополис 2"
    assert item.dub == "Дубляж официальный"


def test_scan_and_group_reports_missing_episode(tmp_path: Path):
    (tmp_path / "Demo S01E01.mp4").touch()
    (tmp_path / "Demo S01E03.mp4").touch()
    groups = group_media(scan_folder(tmp_path))
    assert groups[0].title == "Demo"
    assert groups[0].seasons[0].missing_episodes == [2]


def test_group_media_keeps_movies_out_of_season_zero(tmp_path: Path):
    movie_path = tmp_path / "Кино.mp4"
    movie_path.touch()
    groups = group_media(scan_folder(tmp_path))
    assert groups[0].seasons == []
    assert [item.filename for item in groups[0].movies] == ["Кино.mp4"]


def test_scanner_uses_series_folder_when_filename_title_is_only_number(tmp_path: Path):
    folder = tmp_path / "Мандалорец"
    folder.mkdir()
    (folder / "1 S01E01.mp4").touch()
    item = scan_folder(tmp_path)[0]
    assert item.title == "Мандалорец"


def test_metadata_lookup_rejects_numeric_title(tmp_path: Path):
    database = PublisherDatabase(tmp_path / "publisher.sqlite3")
    try:
        result = asyncio.run(MetadataService(database, [StaticMetadataProvider()]).find("1"))
    finally:
        database.close()
    assert result == []


def test_settings_round_trip_uses_utf8(tmp_path: Path):
    path = tmp_path / "settings.json"
    settings = PublisherSettings(
        folder="D:/Медиа",
        chat_id="-1001",
        bot_api_url="http://127.0.0.1:8081",
        selected_destination="Сериалы",
        topic_ids={"Фильмы": "101", "Сериалы": "202"},
    )
    settings.save(path)
    loaded = PublisherSettings.load(path)
    assert loaded.folder == "D:/Медиа"
    assert loaded.chat_id == "-1001"
    assert loaded.bot_api_url == "http://127.0.0.1:8081"
    assert loaded.selected_destination == "Сериалы"
    assert loaded.topic_ids == {"Фильмы": "101", "Сериалы": "202"}


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
    assert episode_item.data(0, 256)[0] == "media"
    assert window.publish_button.text() == "Опубликовать выбранное"
    window.close()
    del app


def test_main_window_renders_movie_without_fake_season(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from media_publisher.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    movie = MediaFileInfo(
        path=tmp_path / "Кино.mp4",
        filename="Кино.mp4",
        title="Кино",
        media_type="movie",
    )
    window = MainWindow()
    window.show_groups([ShowGroup("Кино", movies=[movie])])

    item = window.tree.topLevelItem(0)
    assert item.text(0) == "Кино"
    assert item.text(1) == "Фильм"
    assert item.text(2) == "Кино.mp4"
    assert item.childCount() == 0
    window.close()
    del app


def test_main_window_keeps_separate_topic_ids(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from media_publisher.gui import main_window

    monkeypatch.setattr(main_window, "default_settings_path", lambda: tmp_path / "settings.json")
    app = QApplication.instance() or QApplication([])
    window = main_window.MainWindow()
    window.thread_edit.setText("101")
    window.destination_combo.setCurrentText("Сериалы")
    window.thread_edit.setText("202")
    window.destination_combo.setCurrentText("Фильмы")
    assert window.thread_edit.text() == "101"
    window.destination_combo.setCurrentText("Сериалы")
    assert window.thread_edit.text() == "202"
    window._save_settings()
    loaded = PublisherSettings.load(tmp_path / "settings.json")
    assert loaded.topic_ids["Фильмы"] == "101"
    assert loaded.topic_ids["Сериалы"] == "202"
    window.close()
    del app


def test_publication_service_sends_movie_to_selected_topic(tmp_path: Path):
    path = tmp_path / "Кино.mp4"
    path.touch()
    movie = MediaFileInfo(path=path, filename=path.name, title="Кино", media_type="movie")
    transport = RecordingTransport()
    service = PublicationService(transport, "-1002208538552", "2")
    result = asyncio.run(service.publish_media(movie))
    assert len(result) == 1
    assert transport.calls == [("video", path, "Кино", "-1002208538552", "2")]


def test_publication_service_sends_single_series_file_without_media_group(tmp_path: Path):
    path = tmp_path / "Demo S01E01.mkv"
    path.touch()
    episode = MediaFileInfo(
        path=path,
        filename=path.name,
        title="Demo",
        season_number=1,
        episode_number=1,
        media_type="series",
    )
    season = SeasonGroup("Demo", 1, [episode])
    transport = RecordingTransport()
    service = PublicationService(transport, "-1001", "149")
    result = asyncio.run(service.publish_season(season))
    assert len(result) == 1
    assert transport.calls[0][0] == "document"
    assert transport.calls[0][-1] == "149"


def test_rezka_parser_extracts_card_fields():
    html = """
    <div class="b-post__title"><h1>Миротворец</h1></div>
    <div class="b-post__origtitle">Peacemaker</div>
    <div class="b-sidecover"><img src="/covers/peace.jpg"></div>
    <table class="b-post__info">
      <tr><td>Год:</td><td>2022</td></tr>
      <tr><td>Страна:</td><td>США</td></tr>
      <tr><td>Жанр:</td><td>Боевик, Комедия</td></tr>
      <tr><td>Режиссер:</td><td>Джеймс Ганн</td></tr>
      <tr><td>В ролях:</td><td>Джон Сина, Даниэль Брукс</td></tr>
    </table>
    <div class="b-post__rating">IMDb: 8.3 (100 000) КиноПоиск: 8.0 (90 000)</div>
    <div class="b-post__description_text">Описание сериала.</div>
    """
    item = RezkaProvider.parse_detail_html(html, "https://rezka.example/series/peace.html")
    assert item.title == "Миротворец"
    assert item.original_title == "Peacemaker"
    assert item.year == "2022"
    assert item.poster_url == "https://rezka.example/covers/peace.jpg"
    assert item.genres == ["Боевик", "Комедия"]
    assert item.cast == ["Джон Сина", "Даниэль Брукс"]
    assert item.imdb_rating == "8.3"
    assert item.kinopoisk_rating == "8.0"
    assert item.overview == "Описание сериала."


def test_rezka_parser_extracts_real_rating_cast_and_best_lists_markup():
    html = """
    <div class="b-post__title"><h1>Монстры-коммандос</h1></div>
    <div class="b-post__origtitle">Creature Commandos</div>
    <div class="b-sidecover"><img src="/poster.jpg"></div>
    <table class="b-post__info">
      <tr><td class="l"><h2>Год</h2>:</td><td>2024</td></tr>
      <tr><td class="l"><h2>Жанр</h2>:</td><td>Боевики, Приключения</td></tr>
      <tr><td class="l"><h2>Рейтинги</h2>:</td><td>
        <span class="b-post__info_rates imdb">IMDb: <span class="bold">7.8</span> <i>(29 181)</i></span>
        <span class="b-post__info_rates kp">Кинопоиск: <span class="bold">7.64</span> <i>(9 130)</i></span>
      </td></tr>
      <tr><td class="l"><h2>Входит в списки</h2>:</td><td class="rd">
        <a href="/best/action/">Лучшие мультфильмы боевики 2024 года</a> (11 место)<br/>
        <a href="/best/fantasy/">Лучшие мультфильмы фэнтези 2024 года</a> (23 место)
      </td></tr>
      <tr><td colspan="2"><div class="persons-list-holder">
        <span itemprop="actor"><span itemprop="name">Индира Варма</span></span>
        <span itemprop="actor"><span itemprop="name">Шон Ганн</span></span>
      </div></td></tr>
    </table>
    <div class="b-post__description_text">Описание мультсериала.</div>
    """
    item = RezkaProvider.parse_detail_html(html, "https://rezka.example/cartoons/commandos.html")
    assert item.imdb_rating == "7.8"
    assert item.imdb_votes == "29 181"
    assert item.kinopoisk_rating == "7.64"
    assert item.kinopoisk_votes == "9 130"
    assert item.cast == ["Индира Варма", "Шон Ганн"]
    assert item.rankings == [
        "Лучшие мультфильмы боевики 2024 года (11 место)",
        "Лучшие мультфильмы фэнтези 2024 года (23 место)",
    ]


def test_rezka_search_does_not_accept_unrelated_homepage_cards():
    html = """
    <div class="b-content__inline_item">
      <div class="b-content__inline_item-link"><a href="/wrong.html">Мятеж (2026)</a></div>
    </div>
    <div class="b-content__inline_item">
      <div class="b-content__inline_item-link"><a href="/right.html">Миротворец (2022)</a></div>
    </div>
    """
    assert RezkaProvider._parse_search_links(html, "https://rezka.example", "Миротворец") == [
        "https://rezka.example/right.html"
    ]


def test_rezka_anubis_pow_solver_matches_required_prefix():
    digest, nonce = _solve_anubis_pow("test-seed", 2)
    assert digest.startswith("00")
    assert nonce >= 0


def test_metadata_cache_preserves_all_search_choices(tmp_path: Path):
    database = PublisherDatabase(tmp_path / "publisher.sqlite3")
    try:
        first = asyncio.run(MetadataService(database, [StaticMetadataProvider()]).find("Demo"))
        second = asyncio.run(MetadataService(database, []).find("Demo"))
    finally:
        database.close()
    assert [item.year for item in first] == ["2025", "2026"]
    assert [item.year for item in second] == ["2025", "2026"]


def test_publication_sends_metadata_card_before_movie(tmp_path: Path):
    path = tmp_path / "Кино.mp4"
    path.touch()
    movie = MediaFileInfo(path=path, filename=path.name, title="Кино", media_type="movie")
    metadata = Metadata(title="Кино", year="2025", overview="Описание", poster_url="https://example.test/poster.jpg")
    transport = RecordingTransport()
    service = PublicationService(transport, "-1001", "2")
    result = asyncio.run(service.publish_media(movie, metadata=metadata))
    assert len(result) == 2
    assert transport.calls[0][0] == "photo"
    assert "Кино — 2025" in transport.calls[0][2]
    assert transport.calls[1][0] == "video"


def test_confirmed_metadata_selection_is_reused(tmp_path: Path):
    database = PublisherDatabase(tmp_path / "publisher.sqlite3")
    selected = Metadata(title="Мандалорец", external_id="82856", source="TMDB")
    try:
        service = MetadataService(database, [StaticMetadataProvider()])
        service.save_selection("Мандалорец", 1, selected)
        result = asyncio.run(service.find("Мандалорец", 1))
    finally:
        database.close()
    assert len(result) == 1
    assert result[0].external_id == "82856"


def test_templates_render_complete_season_card_and_media_caption():
    renderer = TemplateRenderer()
    metadata = Metadata(
        title="Миротворец", season_year="2025", imdb_rating="8.3", imdb_votes="123 456",
        genres=["Боевик", "Комедия"], cast=["Джон Сина"], dub="HDrezka Studio",
        rankings=["Лучшие сериалы 2025 года (3 место)"], season_overview="Описание второго сезона.",
    )
    season = SeasonGroup("Миротворец", 2, dub="HDrezka Studio")
    card = renderer.season(metadata, season)
    media = renderer.media_group(season, 1, 8)
    assert "Миротворец — 2 сезон — 2025" in card
    assert "Рейтинги:" in card
    assert "IMDb: 8.3 (123 456)" in card
    assert "В ролях: Джон Сина" in card
    assert "HDrezka Studio" in card
    assert "Лучшие сериалы 2025 года (3 место)" in card
    assert "Описание второго сезона." in card
    assert media == "2 сезон\nСерии 1-8\nДубляж: HDrezka Studio"


def test_publication_retry_does_not_send_card_twice(tmp_path: Path):
    class FailFirstGroupTransport(RecordingTransport):
        def __init__(self):
            super().__init__()
            self.failed = False

        async def send_media_group(self, files, caption, chat_id, thread_id=""):
            self.calls.append(("group", files, caption, chat_id, thread_id))
            if not self.failed:
                self.failed = True
                raise RuntimeError("temporary error")
            return [{"message_id": index + 1} for index in range(len(files))]

    paths = []
    episodes = []
    for number in (1, 2):
        path = tmp_path / f"Demo S01E{number:02}.mp4"
        path.touch()
        paths.append(path)
        episodes.append(MediaFileInfo(path=path, filename=path.name, title="Demo", season_number=1, episode_number=number, media_type="series"))
    metadata = Metadata(title="Demo", poster_url="https://example.test/poster.jpg")
    database = PublisherDatabase(tmp_path / "publisher.sqlite3")
    transport = FailFirstGroupTransport()
    key = PublicationService.make_operation_key("-1001", "149", paths, metadata)
    service = PublicationService(transport, "-1001", "149", database, key)
    try:
        try:
            asyncio.run(service.publish_season(SeasonGroup("Demo", 1, episodes), metadata=metadata))
        except RuntimeError:
            pass
        asyncio.run(service.publish_season(SeasonGroup("Demo", 1, episodes), metadata=metadata))
    finally:
        database.close()
    assert [call[0] for call in transport.calls].count("photo") == 1
    assert [call[0] for call in transport.calls].count("group") == 2


def test_long_card_is_sent_as_photo_caption_and_continuation_before_video(tmp_path: Path):
    path = tmp_path / "Кино.mp4"
    path.touch()
    movie = MediaFileInfo(path=path, filename=path.name, title="Кино", media_type="movie")
    metadata = Metadata(
        title="Кино", year="2025", poster_url="https://example.test/poster.jpg",
        overview="Очень длинное описание. " * 100,
    )
    transport = RecordingTransport()
    result = asyncio.run(PublicationService(transport, "-1001", "2").publish_media(movie, metadata=metadata))
    assert len(result) == 3
    assert [call[0] for call in transport.calls] == ["photo", "message", "video"]
    assert len(transport.calls[0][2]) <= 1024
    assert "Очень длинное описание" in transport.calls[1][1]


def test_card_text_split_respects_telegram_limits_without_losing_tail():
    text = ("Строка карточки с данными\n" * 300) + "КОНЕЦ"
    parts = PublicationService.card_parts(text)
    assert len(parts[0]) <= 1024
    assert all(len(part) <= 4096 for part in parts[1:])
    assert parts[-1].endswith("КОНЕЦ")


def test_cloud_bot_api_rejects_large_file_before_upload(tmp_path: Path):
    path = tmp_path / "large.mp4"
    with path.open("wb") as handle:
        handle.truncate(51 * 1024 * 1024)
    transport = BotApiTransport("test-token")
    try:
        transport.validate_uploads([path])
    except TelegramApiError as exc:
        message = str(exc)
    else:
        raise AssertionError("Cloud upload limit was not enforced")
    assert "51.0 МБ" in message
    assert "локальный Bot API server" in message


def test_local_bot_api_accepts_file_under_two_gigabytes(tmp_path: Path):
    path = tmp_path / "episode.mp4"
    with path.open("wb") as handle:
        handle.truncate(220 * 1024 * 1024)
    transport = BotApiTransport("test-token", api_url="http://127.0.0.1:8081")
    transport.validate_uploads([path])


def test_size_preflight_happens_before_poster_is_sent(tmp_path: Path):
    class LimitedTransport(RecordingTransport):
        def validate_uploads(self, paths):
            raise TelegramApiError("слишком большой файл")

    path = tmp_path / "movie.mp4"
    path.touch()
    movie = MediaFileInfo(path=path, filename=path.name, title="Кино", media_type="movie")
    transport = LimitedTransport()
    try:
        asyncio.run(PublicationService(transport, "-1001").publish_media(movie, metadata=Metadata(title="Кино", poster_url="poster")))
    except TelegramApiError:
        pass
    else:
        raise AssertionError("Expected preflight failure")
    assert transport.calls == []


def test_retry_after_failed_text_continuation_does_not_duplicate_photo(tmp_path: Path):
    class FailContinuationOnceTransport(RecordingTransport):
        def __init__(self):
            super().__init__()
            self.failed = False

        async def send_message(self, text, chat_id, thread_id=""):
            self.calls.append(("message", text, chat_id, thread_id))
            if not self.failed:
                self.failed = True
                raise RuntimeError("temporary message error")
            return {"message_id": 2}

    path = tmp_path / "movie.mp4"
    path.touch()
    movie = MediaFileInfo(path=path, filename=path.name, title="Кино", media_type="movie")
    metadata = Metadata(title="Кино", poster_url="poster", overview="Длинное описание. " * 100)
    database = PublisherDatabase(tmp_path / "publisher.sqlite3")
    transport = FailContinuationOnceTransport()
    key = PublicationService.make_operation_key("-1001", "2", [path], metadata)
    service = PublicationService(transport, "-1001", "2", database, key)
    try:
        try:
            asyncio.run(service.publish_media(movie, metadata=metadata))
        except RuntimeError:
            pass
        asyncio.run(service.publish_media(movie, metadata=metadata))
    finally:
        database.close()
    assert [call[0] for call in transport.calls].count("photo") == 1
    assert [call[0] for call in transport.calls].count("message") == 2
    assert [call[0] for call in transport.calls].count("video") == 1
