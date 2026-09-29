import asyncio
import json
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


@pytest.mark.parametrize("theme", ["glass", "expressive", "classic"])
def test_admin_panel_offers_new_interface_themes(theme):
    page = admin_api.ADMIN_PANEL_HTML
    assert f'<option value="{theme}"' in page
    assert f'body.theme-{theme}' in page
