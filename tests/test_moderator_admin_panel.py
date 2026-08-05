from app.keyboards import chat_admin_menu, moderator_demote_menu, moderator_panel_menu


def _button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _button_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_moderator_panel_is_owner_only_in_chat_menu() -> None:
    owner_menu = chat_admin_menu(-100, include_access=True)
    delegated_menu = chat_admin_menu(-100, include_access=False)

    assert "Модераторы" in _button_texts(owner_menu)
    assert "Модераторы" not in _button_texts(delegated_menu)


def test_moderator_panel_has_role_and_demote_actions() -> None:
    callbacks = _button_callbacks(moderator_panel_menu(-100))

    assert "mod:role:-100:assistant" in callbacks
    assert "mod:role:-100:moderator" in callbacks
    assert "mod:role:-100:senior" in callbacks
    assert "mod:demote:-100" in callbacks


def test_moderator_demote_menu_lists_current_moderators() -> None:
    markup = moderator_demote_menu(
        -100,
        [{"user_id": 42, "username": "helper", "full_name": "Helper", "role": "assistant"}],
    )

    assert "mod:drop:-100:42" in _button_callbacks(markup)
    assert "Ввести @ или id" in _button_texts(markup)
