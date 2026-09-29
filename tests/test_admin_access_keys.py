import asyncio
import json
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import admin_api


def test_owner_can_issue_login_and_revoke_key(tmp_path, monkeypatch):
    key_file = tmp_path / "admin_access_keys.json"
    config = SimpleNamespace(owner_id=10, bot_admin_ids={10})
    monkeypatch.setattr(admin_api, "access_key_store_path", lambda: str(key_file))
    monkeypatch.setattr(admin_api, "load_config", lambda: config)
    monkeypatch.setattr(admin_api, "admin_api_key", lambda: "master-key")
    admin_api.SESSION_TOKENS.clear()
    actor = admin_api.CURRENT_ADMIN_ACTOR_ID.set(10)
    try:
        created = admin_api.create_access_key(admin_api.AccessKeyCreatePayload(label=" Owner phone ", userId=10))
        assert created["label"] == "Owner phone"
        raw_key = created["accessKey"]
        stored = json.loads(key_file.read_text(encoding="utf-8"))
        assert raw_key not in key_file.read_text(encoding="utf-8")
        assert stored[0]["keyHash"] == admin_api.hash_secret(raw_key)

        session = admin_api.auth_login(admin_api.AccessLoginPayload(accessKey=raw_key))
        token = session["sessionToken"]
        asyncio.run(admin_api.require_admin(f"Bearer {token}"))
        assert admin_api.current_actor_id() == 10

        admin_api.revoke_access_key(created["id"])
        with pytest.raises(HTTPException) as error:
            asyncio.run(admin_api.require_admin(f"Bearer {token}"))
        assert error.value.status_code == 401
    finally:
        admin_api.CURRENT_ADMIN_ACTOR_ID.reset(actor)
        admin_api.SESSION_TOKENS.clear()


@pytest.mark.parametrize("label,user_id", [("  ", 10), ("test", 0), ("test", -5)])
def test_access_key_requires_label_and_positive_telegram_id(label, user_id):
    with pytest.raises(ValidationError):
        admin_api.AccessKeyCreatePayload(label=label, userId=user_id)


def test_access_ui_links_permissions_to_key_issuance():
    page = admin_api.ADMIN_PANEL_HTML
    assert 'id="permissionUserId"' in page
    assert 'onclick="openAccessKeys()"' in page
    assert 'id="accessKeyLabel"' in page
    assert 'id="accessKeyUserId"' in page


@pytest.mark.parametrize("theme", ["glass", "expressive", "warm", "classic"])
def test_admin_panel_offers_new_interface_themes(theme):
    page = admin_api.ADMIN_PANEL_HTML
    assert f'<option value="{theme}"' in page
    assert f'body.theme-{theme}' in page


def test_abstergo_groups_controls_and_combines_auto_replies():
    page = admin_api.ADMIN_PANEL_HTML
    menu = page.split("const defaultActions = [", 1)[1].split("];", 1)[0]
    assert '{ id: "replies", title: "Автоответы" }' in menu
    assert '{ id: "addReply"' not in menu
    assert '{ id: "deleteReply"' not in menu
    for title in ("Ответы и контент", "Группа и модерация", "Управление"):
        assert f'title: "{title}"' in page
    assert 'if (id === "replies") return' in page
    assert 'canWrite("addReply")' in page
    assert 'canWrite("deleteReply")' in page
    assert 'showAction("replies", "Автоответы")' in page
    assert '["addReply", "deleteReply"].includes(id) ? "replies" : id' in page


def test_abstergo_removes_green_theme_and_matches_miniapp_palette():
    page = admin_api.ADMIN_PANEL_HTML
    assert '<option value="green"' not in page
    assert 'body.theme-green' not in page
    assert 'if (theme === "green") return "expressive"' in page
    assert '--bg: #111423;' in page  # M3 Expressive
    assert '--bg: #050b13;' in page  # Liquid Glass
    assert '--bg: #008080;' in page  # Classic


def test_abstergo_warm_theme_keeps_existing_actions_and_group_selection():
    page = admin_api.ADMIN_PANEL_HTML
    assert '<option value="warm"' in page
    assert 'body.theme-warm' in page
    assert 'id="warmGroupSelect"' in page
    assert 'id="warmNav"' in page
    assert 'onclick="warmNavigate(\'groups\')"' in page
    assert 'body.theme-warm #chats { grid-template-columns: 1fr; gap: 0; }' in page
    assert 'class="warm-chat-badge warm-only"' in page
    assert 'theme === "warm" ? "Группы" : "Выбор группы"' in page
    assert 'body.theme-warm #chatTitle { display: none; }' in page
    assert 'body.theme-warm #statusCard { display: none; }' in page
    assert 'id="warmSettingsStatus"' in page
    assert 'subtitle: "Настройка автоответов, триггеров и фильтров"' in page
    assert 'sectionElement.append(heading, subtitle, sectionGrid)' in page
    assert 'const warmActionIcons = {' in page
    assert 'button.innerHTML = `<img class="warm-action-icon"' in page
    assert 'if (theme === "warm") setWarmView(warmView)' in page
    assert 'if (id !== "access" && !canUseAction(id))' in page


@pytest.mark.parametrize("filename", ["abstergo-copper-mark.png", "warm-paper-texture.png", "users.svg"])
def test_abstergo_warm_asset_exists(filename):
    response = admin_api.admin_theme_asset(filename)
    assert response.path.name == filename


def test_abstergo_warm_icon_allowlist_matches_files():
    icon_dir = admin_api.ADMIN_THEME_ASSETS / "abstergo-warm-icons"
    for icon_name in admin_api.ADMIN_WARM_ICON_NAMES:
        assert (icon_dir / f"{icon_name}.svg").is_file()


def test_warm_sections_keep_every_action_and_show_moderation_early():
    page = admin_api.ADMIN_PANEL_HTML
    defaults = page.split("const defaultActions = [", 1)[1].split("];", 1)[0]
    expected = set(re.findall(r'id: "([^"]+)"', defaults)) - {"appSettings"}
    warm = page.split("const warmAdminSections = [", 1)[1].split("];", 1)[0]
    sections = [json.loads(items) for items in re.findall(r'actions: (\[[^\]]+\])', warm)]

    assert sections[0] == ["replies", "triggers", "blacklist"]
    assert sections[1] == ["alarm", "checkAccess"]
    assert set().union(*map(set, sections)) == expected
    assert sum(map(len, sections)) == len(expected)
    assert "activeAdminSections().forEach(section => {" in page
    assert "return activeAdminSections().find(section => section.actions.includes(id));" in page
    assert 'if (overview && visibleMenu && !visibleMenu.classList.contains("hidden")) showMenu();' in page


@pytest.mark.parametrize("filename", ["../admin_api.py", "missing.svg", "unknown.png"])
def test_abstergo_warm_asset_rejects_unknown_filename(filename):
    with pytest.raises(HTTPException) as error:
        admin_api.admin_theme_asset(filename)
    assert error.value.status_code == 404
