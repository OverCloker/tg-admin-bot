import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .media_processor import find_ffmpeg


YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\s]+|youtube\.com/shorts/[^\s?]+(?:\?[^\s]+)?|youtu\.be/[^\s?]+(?:\?[^\s]+)?|music\.youtube\.com/watch\?[^\s]+)",
    re.IGNORECASE,
)
INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p)/[^\s?/#]+(?:[^\s]*)?",
    re.IGNORECASE,
)
SUPPORTED_MEDIA_URL_RE = re.compile(
    rf"(?:{YOUTUBE_URL_RE.pattern})|(?:{INSTAGRAM_URL_RE.pattern})",
    re.IGNORECASE,
)
DOWNLOAD_TYPES = {"video_mp4", "audio_mp3", "music_mp3", "music_m4a"}


@dataclass(frozen=True)
class YoutubeInfo:
    url: str
    title: str
    duration: int | None
    estimated_size: int
    is_music: bool


class YoutubeMediaError(ValueError):
    pass


def media_output_filename(title: str, output_path: str) -> str:
    suffix = Path(output_path).suffix.lower()
    clean_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    clean_title = re.sub(r"\s+", " ", clean_title).strip(" .")
    if not clean_title:
        clean_title = "media"
    return f"{clean_title[:120].rstrip()}{suffix}"


def extract_youtube_url(text: str | None) -> str | None:
    match = YOUTUBE_URL_RE.search(text or "")
    return match.group(0).rstrip(".,);]") if match else None


def extract_instagram_url(text: str | None) -> str | None:
    match = INSTAGRAM_URL_RE.search(text or "")
    return match.group(0).rstrip(".,);]") if match else None


def extract_supported_media_url(text: str | None) -> str | None:
    match = SUPPORTED_MEDIA_URL_RE.search(text or "")
    return match.group(0).rstrip(".,);]") if match else None


def is_youtube_music(url: str) -> bool:
    return urlparse(url).hostname == "music.youtube.com"


def is_instagram_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("instagram.com")


def friendly_error(exc: Exception) -> YoutubeMediaError:
    text = str(exc)
    lowered = text.lower()
    if "private video" in lowered or "sign in" in lowered or "login" in lowered:
        return YoutubeMediaError("Видео требует авторизацию или является приватным.")
    if "not available in your country" in lowered or "geo" in lowered:
        return YoutubeMediaError("Контент недоступен в регионе сервера.")
    if "video unavailable" in lowered or "removed" in lowered:
        return YoutubeMediaError("Видео удалено или недоступно.")
    if "copyright" in lowered or "drm" in lowered:
        return YoutubeMediaError("Контент защищён ограничениями доступа и не может быть скачан.")
    if "http error 403" in lowered or "forbidden" in lowered:
        return YoutubeMediaError(
            "YouTube временно отказал в загрузке файла. Попробуйте ещё раз через несколько минут."
        )
    return YoutubeMediaError("Не получилось получить данные YouTube. Проверьте ссылку и доступность видео.")


def _is_retryable_download_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return any(
        marker in lowered
        for marker in (
            "http error 403",
            "http error 429",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
            "forbidden",
            "connection reset",
            "read timed out",
            "remote end closed connection",
        )
    )


def _download_attempts(base_options: dict, url: str):
    yield base_options
    if not is_instagram_url(url):
        alternate = dict(base_options)
        alternate["extractor_args"] = {"youtube": {"player_client": ["android_vr"]}}
        yield alternate
        yield dict(base_options)


def inspect_youtube(url: str, download_type: str | None = None) -> YoutubeInfo:
    if not extract_supported_media_url(url):
        raise YoutubeMediaError("Поддерживаются ссылки YouTube, YouTube Music и Instagram Reels.")
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise friendly_error(exc) from exc
    formats = info.get("formats") or []
    sizes: list[int] = []
    video_sizes: list[int] = []
    audio_sizes: list[int] = []
    for item in formats:
        if download_type == "video_mp4" and (item.get("height") or 0) > 720:
            continue
        if download_type in {"audio_mp3", "music_mp3", "music_m4a"} and item.get("vcodec") not in {None, "none"}:
            continue
        size = item.get("filesize") or item.get("filesize_approx")
        if size:
            sizes.append(int(size))
            if item.get("vcodec") not in {None, "none"}:
                video_sizes.append(int(size))
            if item.get("acodec") not in {None, "none"}:
                audio_sizes.append(int(size))
    if download_type == "video_mp4" and video_sizes:
        estimated = max(video_sizes) + max(audio_sizes, default=0)
    else:
        estimated = max(sizes, default=int(info.get("filesize") or info.get("filesize_approx") or 0))
    duration = int(info["duration"]) if info.get("duration") else None
    if estimated <= 0 and duration:
        estimated = duration * (24_000 if download_type in {"audio_mp3", "music_mp3", "music_m4a"} else 300_000)
    return YoutubeInfo(
        url=url,
        title=str(info.get("title") or "YouTube media"),
        duration=duration,
        estimated_size=estimated,
        is_music=is_youtube_music(url),
    )


def download_youtube(url: str, download_type: str, task_id: int) -> str:
    if download_type not in DOWNLOAD_TYPES:
        raise YoutubeMediaError("Неизвестный формат скачивания.")
    root = Path("downloads")
    output_dir = root / "youtube"
    temp_dir = root / "temp" / f"task_{task_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_dir = str(Path(find_ffmpeg()).parent)
    output_template = str(temp_dir / "%(title).120B [%(id)s].%(ext)s")
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "ffmpeg_location": ffmpeg_dir,
        "outtmpl": output_template,
        "restrictfilenames": True,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
    }
    if is_instagram_url(url) and download_type != "video_mp4":
        raise YoutubeMediaError("Instagram Reels можно скачать только как MP4.")
    if is_instagram_url(url):
        options.update({
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
        })
        suffix = ".mp4"
    elif download_type == "video_mp4":
        options.update({
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
            "merge_output_format": "mp4",
        })
        suffix = ".mp4"
    elif download_type in {"audio_mp3", "music_mp3"}:
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        })
        suffix = ".mp3"
    else:
        options.update({
            "format": "bestaudio[ext=m4a]/bestaudio",
            "remuxvideo": "m4a",
        })
        suffix = ".m4a"
    last_error: DownloadError | None = None
    for attempt_number, attempt_options in enumerate(_download_attempts(options, url), start=1):
        try:
            with YoutubeDL(attempt_options) as ydl:
                ydl.extract_info(url, download=True)
            last_error = None
            break
        except DownloadError as exc:
            last_error = exc
            for partial in temp_dir.iterdir():
                if partial.is_file():
                    partial.unlink(missing_ok=True)
                elif partial.is_dir():
                    shutil.rmtree(partial, ignore_errors=True)
            if not _is_retryable_download_error(exc):
                break
            if attempt_number < 3:
                time.sleep(attempt_number)
    if last_error is not None:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if is_instagram_url(url):
            raise YoutubeMediaError("Не получилось скачать Instagram Reels. Проверьте, что ссылка публичная и доступна без входа в Instagram.") from last_error
        raise friendly_error(last_error) from last_error
    files = sorted(temp_dir.glob(f"*{suffix}"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise YoutubeMediaError("yt-dlp завершил работу, но итоговый файл не найден.")
    source = files[0]
    target = output_dir / f"task_{task_id}{suffix}"
    shutil.move(str(source), target)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return str(target)


def cleanup_youtube_file(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
