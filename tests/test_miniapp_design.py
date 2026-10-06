"""Guard navigation and accessibility contracts of the refreshed Mini App."""
from app.miniapp_ui import MINI_APP_HTML


def test_admin_entries_keep_all_existing_destinations():
    entries = MINI_APP_HTML.split('function adminSectionHtml(section)', 1)[1].split('async function showAdminPanel()', 1)[0]
    for action in (
        'showRoleManager', 'showAccessManager', 'showModeratorRoleManager',
        'showMineAdmin', 'showModerationManager', 'showBlacklistManager',
        'showRulesManager', 'showTriggerManager', 'showMacroManager', 'showInlineStatistics',
    ):
        assert f'"{action}()"' in entries
    assert 'section.enabled && !!entry' in entries
    assert 'section.enabled && group.keys.includes(section.key)' in entries
    assert 'escapeHtml(section.title || section.key)' in entries
    assert 'aria-hidden="true"' in entries
    assert '"disabled"' in entries


def test_motion_respects_preferences_and_does_not_animate_mine_moves():
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)")' in MINI_APP_HTML
    assert 'reducedMotion.matches || activeView === "mine"' in MINI_APP_HTML
    assert '.observe(content, {childList: true})' in MINI_APP_HTML
    assert 'content.getAnimations().forEach(animation => animation.cancel())' in MINI_APP_HTML
    assert '@media (prefers-reduced-motion: reduce)' in MINI_APP_HTML
    assert '-webkit-tap-highlight-color: transparent' in MINI_APP_HTML
    assert 'button:focus-visible, summary:focus-visible' in MINI_APP_HTML


def test_profile_help_is_collapsible_without_removing_content():
    assert '<details class="panel profile-help"><summary>Команды отношений</summary>' in MINI_APP_HTML
    assert '<b>расстаться</b>' in MINI_APP_HTML
    assert '.top-profile { min-height: 44px; }' in MINI_APP_HTML
    assert 'body:not([data-theme="classic"]) .theme-switch-track' in MINI_APP_HTML


def test_all_themes_share_profile_structure_and_permission_gate():
    profile = MINI_APP_HTML.split('function renderProfile(profile)', 1)[1].split('function showFriendsInfo()', 1)[0]
    assert 'currentMiniTheme()' not in profile  # no theme-specific navigation branches
    assert '${isSelf ? profileServicesHtml() : ""}' in profile
    assert '${isSelf ? profileNavigationHtml(viewer) : ""}' in profile
    assert profile.index('profileServicesHtml()') < profile.index('profileNavigationHtml(viewer)')
    navigation = MINI_APP_HTML.split('function profileNavigationHtml(viewer)', 1)[1].split('function profileServicesHtml()', 1)[0]
    assert 'viewer && viewer.canViewAdminPanel' in navigation
    assert navigation.index('entry("showMine"') < navigation.index('entry("showAdminPanel"') < navigation.index('entry("showBag"')
    assert 'showWardrobe()' in profile and "showShop('gifts')" in profile
    assert 'showFriendsInfo()' in profile


def test_seasonal_effects_are_non_interactive_bounded_and_pause():
    assert '<canvas id="seasonalWeather" aria-hidden="true"></canvas>' in MINI_APP_HTML
    assert '#seasonalWeather { position: fixed; inset: 0; z-index: 0; pointer-events: none;' in MINI_APP_HTML
    assert 'Math.min(window.devicePixelRatio || 1, 1.5)' in MINI_APP_HTML
    assert 'reducedMotion.matches || document.hidden || !seasonalContext' in MINI_APP_HTML
    assert 'cancelAnimationFrame(seasonalFrame)' in MINI_APP_HTML
    assert 'document.addEventListener("visibilitychange", syncSeasonalMotion)' in MINI_APP_HTML
    assert 'reducedMotion.addEventListener("change", syncSeasonalMotion)' in MINI_APP_HTML
    assert 'if (seasonalTheme === theme) return' in MINI_APP_HTML
    assert '/admin/theme-assets/winter-forest.png' in MINI_APP_HTML
    assert '/admin/theme-assets/autumn-courtyard.png' in MINI_APP_HTML


def test_theme_picker_keeps_old_keys_but_has_clear_new_names():
    assert 'glass: "Зимняя"' in MINI_APP_HTML
    assert 'expressive: "Осенняя"' in MINI_APP_HTML
    assert 'const savedTheme = loadMiniSettings().theme || "glass"' in MINI_APP_HTML
    assert 'savedTheme === "neon" ? "classic" : savedTheme' in MINI_APP_HTML
    assert 'role="group" aria-label="Тема интерфейса"' in MINI_APP_HTML
    assert '.theme-option input:focus-visible + label' in MINI_APP_HTML


def test_new_seasons_and_real_flame_frames_keep_common_layout():
    for name in ('spring: "Весенняя"', 'summer: "Летняя"', 'spring-garden.png', 'summer-lake.png'):
        assert name in MINI_APP_HTML
    assert 'campfire-frames.png' in MINI_APP_HTML
    assert 'Math.floor(time / 85) % 16' in MINI_APP_HTML
    assert 'seasonalContext.drawImage(flameAtlas' in MINI_APP_HTML
    assert 'clipPath = `ellipse' not in MINI_APP_HTML
    assert 'campfire-flicker' not in MINI_APP_HTML


def test_cats_are_opt_in_nonblocking_persistent_and_bounded():
    assert 'loadMiniSettings().cats === true' in MINI_APP_HTML
    assert 'settings.cats = catEnabled' in MINI_APP_HTML
    assert 'id="catMode" type="checkbox" role="switch"' in MINI_APP_HTML
    assert 'pointer-events: none; width: 180px' in MINI_APP_HTML
    assert 'catCompanion?.sync(catEnabled)' in MINI_APP_HTML
    assert 'if (!catEnabled || document.hidden)' in MINI_APP_HTML
    assert 'catMeow.play().catch(() => {})' in MINI_APP_HTML
    assert '${isSelf ? catSettingsHtml() : ""}' in MINI_APP_HTML


def test_cat_3d_is_lazy_local_and_preserves_input_and_lifecycle():
    from pathlib import Path
    assets = Path(__file__).resolve().parents[1] / 'app/assets/themes'
    runtime = (assets / 'cat-companion.js').read_text(encoding='utf-8')
    assert 'import("/admin/theme-assets/cat-companion.bundle.js?v=3d-v4")' in MINI_APP_HTML
    assert 'catCompanion || catLoading || !catEnabled || catDestroyed' in MINI_APP_HTML
    assert 'realistic-cat-poses-v2.png' not in MINI_APP_HTML
    assert 'if (event.persisted)' in MINI_APP_HTML
    assert 'window.addEventListener("pageshow", syncCatMode)' in MINI_APP_HTML
    assert 'owner-cat-v4.glb' in runtime
    assert 'cancelAnimationFrame(frame)' in runtime
    assert 'if (!reducedMotion.matches)' in runtime
    assert 'document.hidden' in runtime
    assert "pivot.rotation.set(0, yaw, 0, 'YXZ')" in runtime
    assert 'stand *' not in runtime
    assert 'const targetYaw = s.reduced ? s.facing*.35 : s.heading' in runtime
    assert 'curl * (front ?' not in runtime
    assert "turn('spine_02', 0, curl" not in runtime
    assert (assets / 'owner-cat-v4.glb').stat().st_size < 6_000_000
    assert (assets / 'cat-companion.bundle.js').stat().st_size < 1_000_000
    assert '}, {capture: true}); // Read bounds before a button replaces the current screen.' in MINI_APP_HTML
    assert 'window.visualViewport?.addEventListener("resize", resizeCatViewport' in MINI_APP_HTML
