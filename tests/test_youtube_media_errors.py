from pathlib import Path

from app import youtube_media
from app.youtube_media import friendly_error


def test_youtube_bot_check_is_not_called_private_video():
    error = friendly_error(Exception("Sign in to confirm you’re not a bot. Use --cookies"))

    assert "подтвердить запрос с сервера" in str(error)
    assert "приватным" not in str(error)


def test_private_video_keeps_authentication_error():
    error = friendly_error(Exception("Private video. Sign in if you've been granted access"))

    assert "приватным" in str(error)


def test_inspection_uses_proxy_only_for_youtube(monkeypatch):
    seen = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            seen.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert not download
            return {"title": "Example", "duration": 20, "formats": []}

    monkeypatch.setenv("YOUTUBE_PROXY_URL", "socks5://host.docker.internal:40001")
    monkeypatch.setattr(youtube_media, "YoutubeDL", FakeYoutubeDL)

    youtube_media.inspect_youtube("https://music.youtube.com/watch?v=dYraLlQzjAA")
    youtube_media.inspect_youtube("https://www.instagram.com/reel/abc123/")

    assert seen[0]["proxy"] == "socks5://host.docker.internal:40001"
    assert "proxy" not in seen[1]


def test_download_uses_proxy_only_for_youtube(monkeypatch, tmp_path):
    seen = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            seen.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert download
            Path(self.options["outtmpl"]).parent.joinpath("sample.mp3").write_bytes(b"audio")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUTUBE_PROXY_URL", "socks5://host.docker.internal:40001")
    monkeypatch.setattr(youtube_media, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(youtube_media, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    result = youtube_media.download_youtube("https://www.youtube.com/watch?v=jNQXAC9IVRw", "audio_mp3", 42)

    assert Path(result).read_bytes() == b"audio"
    assert seen[0]["proxy"] == "socks5://host.docker.internal:40001"
