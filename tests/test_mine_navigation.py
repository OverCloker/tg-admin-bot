from app.keyboards import dig_bag_menu, miniapp_private_menu, user_bag_menu, user_dig_mode_menu


def test_group_dig_mode_uses_callback_and_deep_link() -> None:
    buttons = [button for row in user_dig_mode_menu(-1001).inline_keyboard for button in row]

    assert len(buttons) == 2
    assert [button.text for button in buttons[:2]] == ["Автоматически", "Вручную"]
    assert buttons[0].callback_data == "user:dig:auto:-1001"
    assert buttons[1].url == "https://t.me/ypominanieBot?startapp=mine"
    assert all(button.web_app is None for button in buttons)


def test_group_bag_opens_store_via_private_delivery() -> None:
    button = dig_bag_menu(42).inline_keyboard[0][0]

    assert button.text == "Магазин"
    assert button.url == "https://t.me/ypominanieBot?startapp=shop"
    assert button.web_app is None


def test_private_store_button_opens_shop_view(monkeypatch) -> None:
    monkeypatch.setenv("MINI_APP_URL", "https://example.test/miniapp")
    private_button = miniapp_private_menu("Открыть магазин", view="shop").inline_keyboard[0][0]
    bag_button = user_bag_menu(-1001, 42).inline_keyboard[0][0]

    assert private_button.web_app.url == "https://example.test/miniapp?view=shop"
    assert bag_button.url == "https://t.me/ypominanieBot?startapp=shop"
