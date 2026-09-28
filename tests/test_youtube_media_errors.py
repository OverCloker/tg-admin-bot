from app.youtube_media import friendly_error


def test_youtube_bot_check_is_not_called_private_video():
    error = friendly_error(Exception("Sign in to confirm you’re not a bot. Use --cookies"))

    assert "подтвердить запрос с сервера" in str(error)
    assert "приватным" not in str(error)


def test_private_video_keeps_authentication_error():
    error = friendly_error(Exception("Private video. Sign in if you've been granted access"))

    assert "приватным" in str(error)
