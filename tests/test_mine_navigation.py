from app.keyboards import (
    dig_bag_menu,
    dig_register_menu,
    miniapp_private_menu,
    user_bag_menu,
    user_dig_mode_menu,
    user_mine_menu,
)
from app.miniapp_ui import MINI_APP_HTML


def test_group_dig_mode_uses_callback_and_main_miniapp_link(monkeypatch) -> None:
    monkeypatch.delenv("MINI_APP_SHORT_NAME", raising=False)
    buttons = [button for row in user_dig_mode_menu(-1001, 42).inline_keyboard for button in row]

    assert len(buttons) == 2
    assert [button.text for button in buttons[:2]] == ["Автоматически", "Вручную"]
    assert buttons[0].callback_data == "user:dig:auto:-1001:42"
    assert buttons[1].url == "https://t.me/ypominanieBot?startapp=mine_42"
    assert all(button.web_app is None for button in buttons)


def test_group_mine_callbacks_are_bound_to_message_owner() -> None:
    buttons = [button for row in user_mine_menu(-1001, 42, show_back=False).inline_keyboard for button in row]

    assert [button.callback_data for button in buttons] == [
        "user:dig:mode:-1001:42",
        "user:bag:-1001:42",
        "user:donate:-1001:42",
    ]


def test_group_registration_is_bound_to_requesting_user() -> None:
    button = dig_register_menu(42).inline_keyboard[0][0]

    assert button.callback_data == "dig:register:42"


def test_group_bag_opens_main_miniapp_store(monkeypatch) -> None:
    monkeypatch.delenv("MINI_APP_SHORT_NAME", raising=False)
    button = dig_bag_menu(42).inline_keyboard[0][0]

    assert button.text == "Магазин"
    assert button.url == "https://t.me/ypominanieBot?startapp=shop_42"
    assert button.web_app is None


def test_private_store_button_opens_shop_view(monkeypatch) -> None:
    monkeypatch.setenv("MINI_APP_URL", "https://example.test/miniapp")
    monkeypatch.delenv("MINI_APP_SHORT_NAME", raising=False)
    private_button = miniapp_private_menu("Открыть магазин", view="shop").inline_keyboard[0][0]
    bag_button = user_bag_menu(-1001, 42).inline_keyboard[0][0]

    assert private_button.web_app.url == "https://example.test/miniapp?view=shop"
    assert bag_button.url == "https://t.me/ypominanieBot?startapp=shop_42"
def test_miniapp_handles_deep_links_and_plain_text_results() -> None:
    assert 'telegram.initDataUnsafe.start_param' in MINI_APP_HTML
    assert 'query.get("tgWebAppStartParam")' in MINI_APP_HTML
    assert 'hash.get("tgWebAppStartParam")' in MINI_APP_HTML
    assert 'new URLSearchParams(decodeURIComponent(encodedInitData))' in MINI_APP_HTML
    assert 'function plainText(value)' in MINI_APP_HTML
    assert 'node.textContent = cleanText' in MINI_APP_HTML


def test_current_telegram_url_wins_over_stale_launch_data() -> None:
    url_param = MINI_APP_HTML.index('query.get("tgWebAppStartParam")')
    parsed_launch_data = MINI_APP_HTML.index("telegram.initDataUnsafe && telegram.initDataUnsafe.start_param")

    assert url_param < parsed_launch_data
    assert 'if (initialView === "shop") await showShop();' in MINI_APP_HTML
    assert 'initialView === "shop" && state.registered' not in MINI_APP_HTML
    assert 'normalized.startsWith("shop_")' in MINI_APP_HTML
    assert 'Number(state.userId) !== intendedOwner' in MINI_APP_HTML


def test_miniapp_contains_requested_animations() -> None:
    assert 'overlay.className = "dig-animation"' in MINI_APP_HTML
    assert 'class="cat-figure"' in MINI_APP_HTML
    assert 'class="treasure-chest"' in MINI_APP_HTML
    assert "@keyframes pickaxe-swing" in MINI_APP_HTML
    assert "@keyframes chest-open" in MINI_APP_HTML


def test_shop_deep_link_opens_a_distinct_compact_screen() -> None:
    assert 'setScreenHeader(initialView === "shop" ? "shop"' in MINI_APP_HTML
    assert 'screenTitle.textContent = "🛒 Магазин"' in MINI_APP_HTML
    assert 'setScreenHeader("shop");' in MINI_APP_HTML
    assert 'class="shop-hero"' in MINI_APP_HTML
    assert 'class="shop-products"' in MINI_APP_HTML
    assert "overflow-x: auto" in MINI_APP_HTML
    assert 'class="btn shop-buy"' in MINI_APP_HTML
    assert 'window.scrollTo(0, 0)' in MINI_APP_HTML
    assert 'class="inventory-group"' in MINI_APP_HTML
