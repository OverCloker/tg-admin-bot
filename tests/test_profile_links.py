from app.bot import profile_link


def test_profile_link_uses_user_id_even_when_username_exists() -> None:
    link = profile_link(123456, "somebody", "Some Body")

    assert 'href="tg://openmessage?user_id=123456"' in link
    assert "https://t.me/somebody" not in link
    assert ">@somebody<" in link


def test_profile_link_escapes_label_and_suffix() -> None:
    link = profile_link(42, None, "A < B", " [x<y]")

    assert 'href="tg://openmessage?user_id=42"' in link
    assert "A &lt; B" in link
    assert "[x&lt;y]" in link
