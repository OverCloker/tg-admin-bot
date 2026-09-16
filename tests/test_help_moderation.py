from app.bot import chat_help_text


def test_moderation_help_contains_every_moderation_command() -> None:
    text = chat_help_text("moderation")
    expected_commands = (
        "косяк",
        "затихни @ник",
        "трещи @ник",
        "ударить словарём",
        "-сооб",
        "чат стоп",
        "чат старт",
        "подтвердить",
        "затихни админ",
        "запрет слово",
        "разрешить слово",
        "черный список",
        "модеры",
        "рейтинг модеров",
        "модрейтинг",
        "голос @ник",
        "+помощник",
        "-помощник",
        "+модератор",
        "-модератор",
        "+стМодератор",
        "-стМодератор",
        "+админ",
    )

    for command in expected_commands:
        assert command in text


def test_moderation_help_documents_limits_and_permissions() -> None:
    text = chat_help_text("moderation")

    assert "помощник — 10м" in text
    assert "модератор — 30м" in text
    assert "старший — 1ч" in text
    assert "только админы" in text
    assert "только владелец бота" in text
    assert len(text) < 4096
