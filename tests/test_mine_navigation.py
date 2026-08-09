from app.keyboards import (
    admin_menu,
    dig_bag_menu,
    dig_register_menu,
    main_menu,
    miniapp_private_menu,
    premium_menu,
    user_bag_menu,
    user_dig_mode_menu,
    user_mine_menu,
    user_menu,
)
from app.miniapp_ui import MINI_APP_HTML
from app import bot


class FakeTelegramBadRequest(Exception):
    def __str__(self) -> str:
        return "Telegram server says - Bad Request: message to edit not found"


def test_message_edit_not_found_is_treated_as_missing_target() -> None:
    assert bot.message_edit_target_is_missing(FakeTelegramBadRequest())


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
    ]


def test_group_registration_is_bound_to_requesting_user() -> None:
    button = dig_register_menu(42).inline_keyboard[0][0]

    assert button.callback_data == "dig:register:42"


def test_group_bag_opens_main_miniapp_store(monkeypatch) -> None:
    monkeypatch.delenv("MINI_APP_SHORT_NAME", raising=False)
    buttons = [button for row in dig_bag_menu(42).inline_keyboard for button in row]
    button = buttons[0]

    assert button.text == "Магазин"
    assert button.url == "https://t.me/ypominanieBot?startapp=shop_42"
    assert button.web_app is None
    assert "dig:donate:42" not in {item.callback_data for item in buttons if item.callback_data}


def test_private_store_button_opens_shop_view(monkeypatch) -> None:
    monkeypatch.setenv("MINI_APP_URL", "https://example.test/miniapp")
    monkeypatch.delenv("MINI_APP_SHORT_NAME", raising=False)
    private_button = miniapp_private_menu("Открыть магазин", view="shop").inline_keyboard[0][0]
    bag_button = user_bag_menu(-1001, 42).inline_keyboard[0][0]

    assert private_button.web_app.url == "https://example.test/miniapp?view=shop"
    assert bag_button.url == "https://t.me/ypominanieBot?startapp=shop_42"


def test_home_menu_keeps_tools_in_their_sections() -> None:
    home_buttons = [button for row in main_menu().inline_keyboard for button in row]
    home_callbacks = {button.callback_data for button in home_buttons if button.callback_data}

    assert "gold_ticket:buy" not in home_callbacks
    assert "profile:me" not in home_callbacks
    assert "media:menu" not in home_callbacks
    assert "server:ip" not in home_callbacks
    assert "profile:chat:-1001" in {
        button.callback_data
        for row in user_menu(-1001).inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "media:menu" in {
        button.callback_data
        for row in premium_menu().inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "server:ip" in {
        button.callback_data
        for row in admin_menu().inline_keyboard
        for button in row
        if button.callback_data
    }


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
    assert 'class="cat-figure ${coat}"' in MINI_APP_HTML
    assert 'class="cat-whiskers"' in MINI_APP_HTML
    assert 'class="treasure-chest"' in MINI_APP_HTML
    assert "@keyframes pickaxe-swing" in MINI_APP_HTML
    assert "@keyframes chest-open" in MINI_APP_HTML


def test_ticket_picks_update_in_place_without_scrolling_or_full_render() -> None:
    gold_pick = MINI_APP_HTML.split("async function pickGoldTicket", 1)[1].split(
        "async function startSuperGame", 1
    )[0]
    super_pick = MINI_APP_HTML.split("async function pickSuper", 1)[1].split(
        "async function showBag", 1
    )[0]

    assert "updateGameUi(" in gold_pick and '"gold",' in gold_pick
    assert "updateGameUi(" in super_pick and '"super",' in super_pick
    assert "renderMine()" not in gold_pick
    assert "renderMine()" not in super_pick
    assert "scrollToTop()" not in gold_pick
    assert "scrollToTop()" not in super_pick
    assert "await sleep(700)" not in gold_pick
    assert "await sleep(700)" not in super_pick


def test_miniapp_has_no_close_button() -> None:
    assert 'id="close"' not in MINI_APP_HTML
    assert "telegram.close()" not in MINI_APP_HTML
    assert "handleTopProfileButton()" in MINI_APP_HTML
    assert ">Профиль<" in MINI_APP_HTML


def test_mine_actions_refresh_without_scrolling_to_top() -> None:
    dig_action = MINI_APP_HTML.split("async function startInteractiveDig", 1)[1].split(
        "async function pickMineCell", 1
    )[0]
    cell_action = MINI_APP_HTML.split("async function pickMineCell", 1)[1].split(
        "async function useMineTool", 1
    )[0]
    gold_start = MINI_APP_HTML.split("async function startGoldTicket", 1)[1].split(
        "const sleep", 1
    )[0]
    super_start = MINI_APP_HTML.split("async function startSuperGame", 1)[1].split(
        "async function buySuperGame", 1
    )[0]

    assert "function renderMine(scroll = true)" in MINI_APP_HTML
    assert "renderMine(false)" in dig_action
    assert "renderMine(false)" in cell_action
    assert "renderMine(false)" in gold_start
    assert "renderMine(false)" in super_start
    assert "scrollToTop()" not in dig_action
    assert "scrollToTop()" not in cell_action
    assert "scrollToTop()" not in gold_start
    assert "scrollToTop()" not in super_start


def test_shop_deep_link_opens_a_distinct_compact_screen() -> None:
    assert '["shop", "bag", "profile", "weather", "radio"].includes(initialView)' in MINI_APP_HTML
    assert 'screenTitle.textContent = "🛒 Магазин"' in MINI_APP_HTML
    assert 'setScreenHeader("shop");' in MINI_APP_HTML
    assert 'class="shop-hero"' in MINI_APP_HTML
    assert 'class="shop-products"' in MINI_APP_HTML
    assert "overflow-x: auto" in MINI_APP_HTML
    assert "scrollbar-width: thin" in MINI_APP_HTML
    assert "function enableHorizontalWheelScroll" in MINI_APP_HTML
    assert 'enableHorizontalWheelScroll(".shop-tabs")' in MINI_APP_HTML
    assert 'class="btn shop-buy"' in MINI_APP_HTML
    assert 'window.scrollTo(0, 0)' in MINI_APP_HTML
    assert 'class="inventory-group"' in MINI_APP_HTML


def test_miniapp_has_profile_weather_and_radio_screens() -> None:
    assert '"/miniapp/profile"' in MINI_APP_HTML
    assert "MonkeyDin" not in MINI_APP_HTML
    assert "Загружаю профиль..." in MINI_APP_HTML
    assert 'topProfileButton.textContent = activeView === "profile" ? "Назад" : "Профиль"' in MINI_APP_HTML
    assert 'function returnFromProfile()' in MINI_APP_HTML
    assert 'profileReturnView = activeView || "mine"' in MINI_APP_HTML
    assert 'api(`/miniapp/weather?q=${encodeURIComponent(city)}`)' in MINI_APP_HTML
    assert 'function showWeather()' in MINI_APP_HTML
    assert 'function showRadio()' in MINI_APP_HTML
    assert 'function showFriendsInfo()' in MINI_APP_HTML
    assert 'function profileAvatarHtml(user, cosmetics = {}, small = false)' in MINI_APP_HTML
    assert 'function friendRowHtml(friend)' in MINI_APP_HTML
    assert ".profile-avatar img { position: relative; z-index: 2;" in MINI_APP_HTML
    assert 'social.relation !== "self" && social.relationTitle' in MINI_APP_HTML
    assert "Пока нет друзей из общих чатов." in MINI_APP_HTML
    assert "Пока нет друзей, которые зарегистрированы в шахте." not in MINI_APP_HTML
    assert 'showProfile(${Number(friend.id)})' in MINI_APP_HTML
    assert '`/miniapp/profile?user_id=${encodeURIComponent(userId)}`' in MINI_APP_HTML
    assert 'class="panel profile-hero ${profileHeroClass(cosmetics)}"' in MINI_APP_HTML
    assert 'onclick="showFriendsInfo()">${friends.length ? `Друзья: ${friends.length}` : "Друзья"}</button>' in MINI_APP_HTML
    assert 'function searchRadioStations()' in MINI_APP_HTML
    assert 'miniAppFavoriteRadioStations' in MINI_APP_HTML
    assert 'api(`/miniapp/radio/search?q=${encodeURIComponent(query)}`)' in MINI_APP_HTML
    assert 'station.streamUrl || station.url_resolved || station.url' in MINI_APP_HTML
    assert 'class="persistent-radio"' in MINI_APP_HTML
    assert "Редчайшие достижения" in MINI_APP_HTML
    assert "mine.rareAchievements" in MINI_APP_HTML


def test_miniapp_has_interface_themes() -> None:
    assert 'body[data-theme="material"]' in MINI_APP_HTML
    assert 'body[data-theme="glass"]' in MINI_APP_HTML
    assert "Material You" in MINI_APP_HTML
    assert "Liquid Glass" in MINI_APP_HTML
    assert 'id="themeApple" value="glass"' in MINI_APP_HTML
    assert 'id="themeAndroid" value="material"' in MINI_APP_HTML
    assert "theme-switch-knob" in MINI_APP_HTML
    assert "theme-platform-icon theme-android-icon" in MINI_APP_HTML
    assert "--surface-blur: blur(28px) saturate(1.75)" in MINI_APP_HTML
    assert 'body[data-theme="glass"] .panel::before' in MINI_APP_HTML
    assert "inset 0 1px 0 #ffffff70" in MINI_APP_HTML
    assert "function setMiniTheme(theme)" in MINI_APP_HTML
    assert "themeSwitcherHtml()" in MINI_APP_HTML
    assert 'settings.theme' in MINI_APP_HTML


def test_miniapp_replaces_rank_card_with_two_utility_buttons_on_mine() -> None:
    mine_html = MINI_APP_HTML.split("function mineHtml()", 1)[1].split("function goldTicketHtml()", 1)[0]

    assert "${utilityActionsHtml()}" in mine_html
    assert "${rankCosmeticHtml(false)}" not in mine_html
    assert '<button class="btn secondary" onclick="showWeather()">Погода</button>' in MINI_APP_HTML
    assert '<button class="btn secondary" onclick="showRadio()">Радио</button>' in MINI_APP_HTML


def test_secret_message_command_detects_hidden_text_separately() -> None:
    safe = bot.SECRET_MESSAGE_RE.match("лс @target_user")
    unsafe = bot.SECRET_MESSAGE_RE.match("лс @target_user этот текст нельзя в группу")

    assert safe
    assert safe.group(1) == "@target_user"
    assert safe.group(2) is None
    assert unsafe
    assert unsafe.group(1) == "@target_user"
    assert unsafe.group(2) == "этот текст нельзя в группу"
    assert bot.SECRET_MESSAGE_ALERT_LIMIT <= 200
