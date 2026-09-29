"""Keep the isolated design preview representative of the owner dashboard."""

import runpy
from pathlib import Path


def test_warm_preview_renders_actions_with_fixture_owner_permissions():
    preview = runpy.run_path(str(Path(__file__).with_name("manual_preview_warm.py")))
    html = preview["preview_html"]().decode("utf-8")
    fixture = html.rsplit("const demoChats =", 1)[1]

    assert "ownerActionsAllowed = true;" in fixture
    assert fixture.index("ownerActionsAllowed = true;") < fixture.index("showMenu();")
    assert "overview = {chat: demoChats[0], replies: demoReplies" in fixture
    assert "document.getElementById('chatTitle').textContent = demoChats[0].title;" in fixture


def test_mobile_preview_uses_phone_sized_same_origin_frame():
    preview = runpy.run_path(str(Path(__file__).with_name("manual_preview_warm.py")))
    frame = preview["MOBILE_FRAME"].decode("utf-8")

    assert "width:393px;height:852px" in frame
    assert 'src="/"' in frame
