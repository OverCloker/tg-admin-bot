import os
import shutil
import subprocess
import threading
from pathlib import Path


TASK_OUTPUTS = {
    "extract_audio": ".mp3",
    "audio_convert": ".mp3",
    "video_convert": ".mp4",
    "compress_video": ".mp4",
    "compress_audio": ".mp3",
    "gif_create": ".gif",
    "transcription": ".txt",
    "transcription_timestamps": ".txt",
}

TASK_TITLES = {
    "extract_audio": "Извлечь аудио из видео",
    "audio_convert": "Конвертировать аудио в MP3",
    "video_convert": "Конвертировать видео в MP4",
    "compress_video": "Сжать видео",
    "compress_audio": "Сжать аудио",
    "gif_create": "Сделать GIF из видео",
    "transcription": "Расшифровать аудио в текст",
    "transcription_timestamps": "Расшифровать с таймкодами",
    "youtube_video": "Скачать YouTube-видео MP4",
    "youtube_audio": "Скачать YouTube-аудио MP3",
    "youtube_music_audio": "Скачать YouTube Music-аудио",
    "instagram_reel": "Скачать Instagram Reels MP4",
}

_WHISPER_MODEL = None
_WHISPER_LOCK = threading.Lock()


def find_ffmpeg() -> str:
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = Path(os.getenv("LOCALAPPDATA", ""))
    candidates = sorted(
        local.glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg*/bin/ffmpeg.exe"),
        reverse=True,
    )
    if candidates:
        return str(candidates[0])
    raise RuntimeError("FFmpeg не найден. Установите FFmpeg или задайте FFMPEG_PATH.")


def ffmpeg_available() -> bool:
    try:
        find_ffmpeg()
        return True
    except RuntimeError:
        return False


def whisper_available() -> bool:
    try:
        from faster_whisper import WhisperModel  # noqa: F401
        return True
    except ImportError:
        return False


def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        with _WHISPER_LOCK:
            if _WHISPER_MODEL is None:
                from faster_whisper import WhisperModel

                model_name = os.getenv("WHISPER_MODEL", "small").strip() or "small"
                _WHISPER_MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _WHISPER_MODEL


def timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def transcribe_media(source_path: str, output_path: Path, with_timestamps: bool) -> str:
    model = get_whisper_model()
    segments, info = model.transcribe(
        source_path,
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
    )
    materialized = list(segments)
    lines = [f"Язык: {info.language}", ""]
    if with_timestamps:
        lines.extend(
            f"[{timestamp(segment.start)} - {timestamp(segment.end)}] {segment.text.strip()}"
            for segment in materialized
            if segment.text.strip()
        )
    else:
        text = " ".join(segment.text.strip() for segment in materialized if segment.text.strip())
        lines.append(text or "Речь не распознана.")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)


def process_media(task_type: str, source_path: str, output_dir: str, task_id: int) -> str:
    suffix = TASK_OUTPUTS.get(task_type)
    if not suffix:
        raise ValueError("Эта медиа-операция пока не поддерживается обработчиком FFmpeg.")
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    output = target_dir / f"task_{task_id}{suffix}"
    if task_type in {"transcription", "transcription_timestamps"}:
        return transcribe_media(source_path, output, task_type == "transcription_timestamps")
    ffmpeg = find_ffmpeg()

    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    commands = {
        "extract_audio": common + ["-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(output)],
        "audio_convert": common + ["-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(output)],
        "video_convert": common + ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", str(output)],
        "compress_video": common + ["-c:v", "libx264", "-preset", "medium", "-crf", "30", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output)],
        "compress_audio": common + ["-vn", "-codec:a", "libmp3lame", "-b:a", "96k", str(output)],
        "gif_create": common + ["-vf", "fps=12,scale=640:-1:flags=lanczos", "-loop", "0", str(output)],
    }
    completed = subprocess.run(commands[task_type], capture_output=True, text=True, timeout=1800)
    if completed.returncode != 0 or not output.is_file():
        error = (completed.stderr or completed.stdout or "FFmpeg завершился с ошибкой.").strip()
        raise RuntimeError(error[-1800:])
    return str(output)
