from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app import admin_api, miniapp


@pytest.mark.parametrize("actor", [None, 20, 30])
def test_non_owner_cannot_access_permission_management(actor):
    config = SimpleNamespace(owner_id=10, bot_admin_ids={10, 20})
    token = admin_api.CURRENT_ADMIN_ACTOR_ID.set(actor)
    try:
        with patch.object(admin_api, "load_config", return_value=config):
            with pytest.raises(HTTPException) as error:
                admin_api.list_admin_permissions(chatId=-100)
            assert error.value.status_code == 403
            assert not admin_api.owner_actions_allowed()
    finally:
        admin_api.CURRENT_ADMIN_ACTOR_ID.reset(token)


def test_explicit_owner_does_not_need_legacy_admin_membership():
    config = SimpleNamespace(owner_id=10, bot_admin_ids={20})
    token = admin_api.CURRENT_ADMIN_ACTOR_ID.set(10)
    try:
        with patch.object(admin_api, "load_config", return_value=config):
            admin_api.require_owner_action()
            admin_api.require_owner_only()
    finally:
        admin_api.CURRENT_ADMIN_ACTOR_ID.reset(token)


@pytest.mark.parametrize("actor,allowed", [(10, True), (20, False), (30, False)])
def test_miniapp_roles_and_mine_writes_are_owner_only(actor, allowed):
    with patch.object(miniapp, "_miniapp_owner_id", return_value=10):
        assert miniapp._miniapp_can_manage_roles(actor) is allowed
        assert miniapp._miniapp_can_manage_mine_admin(None, actor) is allowed


def test_missing_owner_never_grants_owner_actions():
    token = admin_api.CURRENT_ADMIN_ACTOR_ID.set(20)
    try:
        with patch.object(admin_api, "load_config", return_value=SimpleNamespace(owner_id=None, bot_admin_ids={20})):
            assert not admin_api.owner_actions_allowed()
    finally:
        admin_api.CURRENT_ADMIN_ACTOR_ID.reset(token)
