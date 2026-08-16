"""HTML interface for the Telegram mine Mini App."""

MINI_APP_HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta http-equiv="Cache-Control" content="no-store">
  <title>Шахта</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1420;
      --panel: #17283a;
      --panel-color: #17283a;
      --panel-2: #20364b;
      --line: #2b455e;
      --text: #f5f7fa;
      --muted: #aeb9c6;
      --accent: #2794d2;
      --accent-2: #e5a64a;
      --ok: #5ecb83;
      --danger: #d95c62;
      --radius: 20px;
      --radius-sm: 14px;
      --button-radius: 18px;
      --input-bg: #0f1c2a;
      --input-placeholder: #9fb0c0;
      --panel-shadow: 0 14px 38px #00000024;
      --surface-blur: none;
      --app-bg-layer: var(--bg);
    }
    body[data-theme="expressive"] {
      --bg: #111423;
      --panel: linear-gradient(145deg, #27334f 0%, #1b283f 52%, #162236 100%);
      --panel-color: #1b283f;
      --panel-2: linear-gradient(145deg, #344667 0%, #223653 100%);
      --line: #6d86b8;
      --text: #fbfcff;
      --muted: #d4dcef;
      --accent: #b8d7ff;
      --accent-2: #ffcb6f;
      --radius: 28px;
      --radius-sm: 20px;
      --button-radius: 999px;
      --input-bg: #16243a;
      --input-placeholder: #bfcae2;
      --panel-shadow:
        0 18px 42px #02071240,
        inset 0 1px 0 #ffffff2f;
      --app-bg-layer:
        radial-gradient(circle at 12% 4%, #7ab8ff8c, transparent 25%),
        radial-gradient(circle at 88% 10%, #ff9cc070, transparent 24%),
        radial-gradient(circle at 24% 82%, #ffd36e55, transparent 28%),
        linear-gradient(145deg, #151b31 0%, #0f1729 46%, #121827 100%),
        var(--bg);
    }
    body[data-theme="glass"] {
      --bg: #050b13;
      --panel:
        linear-gradient(145deg, #ffffff46 0%, #e8f7ff1c 36%, #7aa4d20f 100%);
      --panel-color: #e9f6ff18;
      --panel-2:
        linear-gradient(145deg, #ffffff54 0%, #d8f2ff25 48%, #7794c018 100%);
      --line: #ffffff78;
      --text: #fbfdff;
      --muted: #e5edf6;
      --accent: #d8f1ff;
      --accent-2: #fff6bd;
      --radius: 30px;
      --radius-sm: 22px;
      --button-radius: 999px;
      --input-bg: #1d3149a8;
      --input-placeholder: #d9e7f3;
      --panel-shadow:
        0 34px 90px #00000073,
        0 12px 32px #9de1ff22,
        inset 0 1px 0 #ffffff9e,
        inset 0 -1px 0 #ffffff24,
        inset 0 0 32px #ffffff10;
      --surface-blur: blur(36px) saturate(2.05) contrast(1.04);
      --app-bg-layer:
        radial-gradient(circle at 12% -4%, #ffffff8f, transparent 18%),
        radial-gradient(circle at 78% 2%, #9fe9ff70, transparent 23%),
        radial-gradient(circle at 20% 74%, #8f7dff48, transparent 30%),
        radial-gradient(circle at 94% 84%, #ffffff36, transparent 25%),
        linear-gradient(115deg, transparent 0 18%, #ffffff10 20%, transparent 34%),
        linear-gradient(160deg, #08111d 0%, #0d1829 45%, #05070d 100%),
        var(--bg);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }
    body {
      position: relative;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      padding: max(16px, env(safe-area-inset-top)) 16px max(24px, env(safe-area-inset-bottom));
      background: transparent;
    }
    .app-bg {
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background: var(--app-bg-layer);
      background-size: cover;
      background-position: center top;
      transform: translateZ(0);
    }
    button { font: inherit; }
    main { position: relative; z-index: 1; width: min(100%, 560px); margin: 0 auto; }
    .top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .top-actions { display: flex; align-items: center; gap: 8px; }
    .top-profile {
      width: auto;
      min-height: 38px;
      margin: 0;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: var(--button-radius);
      background: var(--panel-2);
      color: var(--text);
      font-weight: 800;
      white-space: nowrap;
    }
    input::placeholder { color: var(--input-placeholder); opacity: 1; }
    body[data-theme="glass"] .top-profile,
    body[data-theme="glass"] .btn,
    body[data-theme="glass"] .mini-form input,
    body[data-theme="glass"] .role-manager-form input,
    body[data-theme="glass"] .mine-admin-form input,
    body[data-theme="glass"] .mine-admin-form textarea,
    body[data-theme="glass"] .mine-admin-form select,
    body[data-theme="glass"] .persistent-radio {
      border: 1px solid #ffffff4a;
      box-shadow:
        0 12px 34px #0000003d,
        inset 0 1px 0 #ffffff66,
        inset 0 -1px 0 #ffffff18;
      backdrop-filter: var(--surface-blur);
    }
    body[data-theme="glass"] .btn {
      color: #07111c;
      text-shadow: 0 1px 0 #ffffff80;
      background:
        radial-gradient(circle at 28% 12%, #ffffff 0%, #ffffffc8 18%, transparent 38%),
        linear-gradient(180deg, #ffffffee 0%, #dff5ffc8 48%, #a9d8ffa8 100%);
      box-shadow:
        0 14px 34px #00000045,
        inset 0 1px 0 #ffffff,
        inset 0 -2px 5px #6daee03d;
    }
    body[data-theme="glass"] .btn.secondary,
    body[data-theme="glass"] .top-profile {
      color: var(--text);
      text-shadow: 0 1px 2px #001220a8;
      background:
        radial-gradient(circle at 18% 8%, #ffffff5c 0%, transparent 34%),
        var(--panel-2);
    }
    body[data-theme="expressive"] .btn {
      border: 1px solid #ffffff4a;
      color: #091322;
      background:
        linear-gradient(135deg, #ffe08b 0%, #b8d7ff 52%, #d9b8ff 100%);
      box-shadow:
        0 12px 24px #02071242,
        inset 0 1px 0 #ffffffb0;
    }
    body[data-theme="expressive"] .btn.secondary,
    body[data-theme="expressive"] .top-profile {
      color: #fafdff;
      background:
        linear-gradient(145deg, #536f9a 0%, #334f79 54%, #2b4166 100%);
      text-shadow: 0 1px 1px #00122499;
    }
    h1, h2, p { margin-top: 0; }
    h1 { margin-bottom: 2px; font-size: 34px; letter-spacing: 0; }
    h2 { margin-bottom: 10px; font-size: 23px; letter-spacing: 0; }
    .muted { color: var(--muted); }
    .panel {
      position: relative;
      overflow: hidden;
      margin-top: 14px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--panel);
      box-shadow: var(--panel-shadow);
      backdrop-filter: var(--surface-blur);
    }
    body[data-theme="glass"] .panel::before,
    body[data-theme="glass"] .stat::before,
    body[data-theme="glass"] .profile-card::before,
    body[data-theme="glass"] .achievement-card::before,
    body[data-theme="glass"] .inventory-group::before,
    body[data-theme="glass"] .bag-summary::before,
    body[data-theme="glass"] .mine-admin-card::before,
    body[data-theme="glass"] .mine-admin-row::before {
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      border-radius: inherit;
      background:
        linear-gradient(128deg, transparent 0 16%, #ffffff26 21%, #ffffff0d 27%, transparent 38%),
        linear-gradient(292deg, transparent 0 63%, #9de6ff18 72%, transparent 86%),
        radial-gradient(ellipse 180px 58px at 34px 16px, #ffffff32 0%, transparent 74%),
        radial-gradient(ellipse 150px 52px at calc(100% - 28px) 18px, #9de6ff1d 0%, transparent 76%);
      background-repeat: no-repeat;
      mix-blend-mode: screen;
      opacity: .74;
    }
    body[data-theme="glass"] .panel::after,
    body[data-theme="glass"] .stat::after,
    body[data-theme="glass"] .profile-card::after,
    body[data-theme="glass"] .achievement-card::after,
    body[data-theme="glass"] .inventory-group::after,
    body[data-theme="glass"] .bag-summary::after,
    body[data-theme="glass"] .mine-admin-card::after,
    body[data-theme="glass"] .mine-admin-row::after {
      content: "";
      position: absolute;
      left: 18px;
      right: 18px;
      top: 1px;
      height: 2px;
      border-radius: 999px;
      background:
        linear-gradient(90deg, transparent 0%, #ffffffb8 18%, #ffffffec 46%, #ffffff6a 72%, transparent 100%);
      box-shadow:
        0 18px 38px #ffffff2e,
        0 1px 0 #ffffff4f;
      opacity: .82;
      pointer-events: none;
    }
    .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 16px; }
    .stat {
      position: relative;
      overflow: hidden;
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel);
      box-shadow: var(--panel-shadow);
      backdrop-filter: var(--surface-blur);
    }
    .stat b { display: block; margin-top: 4px; font-size: 20px; overflow-wrap: anywhere; }
    .rank-card {
      border-width: 2px;
      background:
        linear-gradient(135deg, color-mix(in srgb, var(--rank-color, #678fb2) 22%, transparent), transparent 58%),
        var(--panel);
      box-shadow: 0 0 0 1px color-mix(in srgb, var(--rank-color, #678fb2) 45%, transparent) inset;
    }
    .rank-card .rank-line { display:flex; align-items:center; gap:10px; font-weight:800; }
    .rank-card .rank-emblem { display:grid; place-items:center; width:42px; height:42px; border-radius:var(--radius-sm); background: color-mix(in srgb, var(--rank-color, #678fb2) 28%, #07111c); font-size:26px; }
    .rank-card.rank-1, .rank-badge.rank-1 { --rank-color:#678fb2; border-color:#678fb2; }
    .rank-card.rank-2, .rank-badge.rank-2 { --rank-color:#62a879; border-color:#62a879; }
    .rank-card.rank-3, .rank-badge.rank-3 { --rank-color:#ce9b49; border-color:#ce9b49; }
    .rank-card.rank-4, .rank-badge.rank-4 { --rank-color:#bc6f88; border-color:#bc6f88; }
    .rank-badge { display:inline-flex; align-items:center; gap:7px; margin-top:10px; padding:7px 10px; border:1px solid var(--line); border-radius:var(--radius-sm); background: color-mix(in srgb, var(--rank-color, #678fb2) 18%, var(--panel-color)); font-size:13px; font-weight:800; }
    .utility-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
    .utility-actions .btn { min-height: 46px; margin: 0; }
    .mini-form { display: grid; gap: 8px; margin-top: 12px; }
    .mini-form input {
      width: 100%;
      min-height: 44px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--input-bg);
      color: var(--text);
      font: inherit;
    }
    .mini-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .mini-row .btn { min-height: 44px; margin: 0; }
    .profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    .profile-card { padding: 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--panel); }
    body[data-theme="glass"] .profile-card,
    body[data-theme="glass"] .achievement-card,
    body[data-theme="glass"] .inventory-group,
    body[data-theme="glass"] .bag-summary,
    body[data-theme="glass"] .mine-admin-card,
    body[data-theme="glass"] .mine-admin-row {
      position: relative;
      overflow: hidden;
      box-shadow: var(--panel-shadow);
      backdrop-filter: var(--surface-blur);
    }
    .profile-card b { display: block; margin-top: 4px; font-size: 18px; overflow-wrap: anywhere; }
    .profile-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
    .profile-actions .btn { margin: 0; min-height: 44px; }
    .profile-hero {
      display: grid;
      grid-template-columns: 88px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
      min-height: 128px;
      background:
        radial-gradient(circle at 18% 0%, color-mix(in srgb, var(--profile-glow, #9ed0ff) 36%, transparent), transparent 38%),
        linear-gradient(135deg, color-mix(in srgb, var(--profile-glow, #9ed0ff) 18%, transparent), transparent 62%),
        var(--panel);
    }
    .profile-hero.bg-lava { --profile-glow: #ff8b52; background:
      radial-gradient(circle at 16% 4%, #ffd18a44, transparent 34%),
      radial-gradient(circle at 88% 92%, #ff4b2c30, transparent 38%),
      linear-gradient(135deg, #35180f, #142334 62%); }
    .profile-hero.bg-old-mine { --profile-glow: #d3a55d; background:
      radial-gradient(circle at 16% 4%, #d3a55d38, transparent 34%),
      linear-gradient(135deg, #2b2217, #132436 62%); }
    .profile-avatar {
      position: relative;
      display: grid;
      place-items: center;
      width: 88px;
      height: 88px;
      overflow: hidden;
      border: 3px solid color-mix(in srgb, var(--profile-glow, #9ed0ff) 72%, #fff);
      border-radius: 28px;
      background: linear-gradient(135deg, #294158, #102033);
      color: #fff;
      font-size: 32px;
      font-weight: 950;
      box-shadow: 0 0 0 1px #ffffff44 inset, 0 12px 28px #0005;
    }
    .profile-avatar.frame-crystal { border-color: #9fdcff; box-shadow: 0 0 24px #78d8ff44, 0 0 0 1px #ffffff66 inset; }
    .profile-avatar.frame-copper { border-color: #d58d54; box-shadow: 0 0 20px #d58d5430, 0 0 0 1px #ffd8af55 inset; }
    .profile-avatar.frame-couple { border-color: #ff8fd1; box-shadow: 0 0 22px #ff8fd144, 0 0 0 1px #ffffff66 inset; }
    .profile-avatar > * { grid-area: 1 / 1; }
    .profile-avatar img { position: relative; z-index: 2; width: 100%; height: 100%; object-fit: cover; background: var(--panel-2); }
    .profile-avatar.has-image .profile-avatar-fallback { display: none; }
    .profile-avatar-fallback { position: relative; z-index: 1; letter-spacing: -.04em; }
    .profile-title { min-width: 0; }
    .profile-title h2 { margin: 0; overflow-wrap: anywhere; }
    .profile-username { margin-top: 3px; color: var(--muted); overflow-wrap: anywhere; }
    .profile-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .profile-badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 9px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: color-mix(in srgb, var(--profile-glow, #9ed0ff) 14%, var(--panel-color));
      font-size: 12px;
      font-weight: 850;
    }
    .profile-badge.owner { border-color:#ffd66d; background:#3a2a10; color:#fff0be; }
    .profile-badge.admin { border-color:#89d8ff; background:#102d45; color:#e5f7ff; }
    .profile-badge.moderation { border-color:#83b7ff; background:#102947; color:#ddecff; }
    .profile-badge.custom { border-color:#b98cff; background:#271946; color:#f2e8ff; }
    .role-manager-form { display: grid; gap: 8px; margin-top: 10px; }
    .role-manager-form input {
      width: 100%;
      min-height: 44px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--input-bg);
      color: var(--text);
      font: inherit;
      box-sizing: border-box;
    }
    .role-list { display: grid; gap: 8px; margin-top: 12px; }
    .role-tabs {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding: 2px 0 8px;
      scrollbar-width: thin;
      scrollbar-color: var(--accent) var(--input-bg);
      scroll-snap-type: x proximity;
    }
    .role-tabs::-webkit-scrollbar { height: 6px; }
    .role-tabs::-webkit-scrollbar-track { background: var(--input-bg); border-radius: 999px; }
    .role-tabs::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 999px; }
    .role-tab {
      flex: 0 0 auto;
      max-width: 220px;
      min-height: 42px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: var(--button-radius);
      background: var(--panel-2);
      color: var(--text);
      font-weight: 850;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      scroll-snap-align: start;
    }
    .role-tab.active {
      border-color: var(--accent);
      background: color-mix(in srgb, var(--accent) 24%, var(--panel-color));
    }
    .role-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel-2);
    }
    .role-row b,
    .role-row span { overflow-wrap: anywhere; }
    .mine-admin-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:8px; margin-top:10px; }
    .mine-admin-card { padding:10px; border:1px solid var(--line); border-radius:var(--radius-sm); background:var(--panel-2); }
    .mine-admin-card b { display:block; margin-top:4px; font-size:18px; }
    .mine-admin-form { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:8px; margin-top:10px; }
    .mine-admin-form input,
    .mine-admin-form textarea,
    .mine-admin-form select {
      width:100%;
      min-height:42px;
      padding:9px 10px;
      border:1px solid var(--line);
      border-radius:var(--radius-sm);
      background:var(--input-bg);
      color:var(--text);
      font:inherit;
      box-sizing:border-box;
    }
    .mine-admin-form textarea { min-height:110px; resize:vertical; }
    .mine-admin-form .wide { grid-column: 1 / -1; }
    .mine-admin-screen { display:grid; gap:14px; }
    .mine-admin-row {
      display:grid;
      grid-template-columns:minmax(0, 1fr);
      gap:8px;
      align-items:center;
      padding:9px 10px;
      border:1px solid var(--line);
      border-radius:var(--radius-sm);
      background:var(--panel-2);
    }
    .mine-admin-row b,
    .mine-admin-row span { min-width:0; overflow-wrap:break-word; word-break:normal; }
    .mine-admin-title {
      display:block;
      min-width:0;
    }
    .mine-admin-title b { overflow-wrap:break-word; }
    .mine-admin-username {
      display:block;
      margin-top:6px;
      color:var(--text);
      font-weight:760;
      line-height:1.2;
      overflow-wrap:anywhere;
    }
    .mine-admin-username-label {
      color:var(--muted);
      font-weight:650;
      margin-right:6px;
    }
    .mine-admin-row > .btn { width:100%; margin:0; }
    .mine-admin-row > .utility-actions {
      width:100%;
      grid-template-columns:repeat(auto-fit, minmax(94px, 1fr));
    }
    .admin-list-row {
      display:grid;
      grid-template-columns:minmax(0, 1fr);
      gap:8px;
      align-items:center;
      padding:9px 10px;
      border:1px solid var(--line);
      border-radius:var(--radius-sm);
      background:var(--panel-2);
    }
    .admin-list-row b,
    .admin-list-row span { min-width:0; overflow-wrap:break-word; word-break:normal; }
    .admin-list-row > .utility-actions {
      width:100%;
      grid-template-columns:repeat(auto-fit, minmax(94px, 1fr));
    }
    .trigger-answer-list { display:grid; gap:8px; }
    .trigger-answer-row { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:8px; align-items:start; }
    .trigger-answer-row textarea { min-height:72px; }
    .trigger-media-box { display:grid; gap:8px; padding:10px; border:1px solid var(--line); border-radius:var(--radius-sm); background:var(--panel-2); }
    .trigger-media-box input[type="file"] { min-height:0; padding:8px; }
    .trigger-media-status { font-size:13px; color:var(--muted); overflow-wrap:anywhere; }
    .friend-list { display: grid; gap: 8px; margin-top: 10px; }
    .friend-row {
      display: grid;
      grid-template-columns: 46px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      width: 100%;
      min-height: 62px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel-2);
      color: var(--text);
      text-align: left;
      cursor: pointer;
    }
    .friend-row .profile-avatar { width: 46px; height: 46px; border-radius: 16px; border-width: 2px; font-size: 18px; }
    .friend-name { min-width: 0; font-weight: 850; overflow-wrap: anywhere; }
    .friend-meta { margin-top: 2px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    .friend-open { color: var(--muted); font-weight: 900; }
    .inventory-groups { display: grid; gap: 10px; margin-top: 10px; }
    .inventory-chip-group { display: grid; gap: 7px; }
    .inventory-chip-title { color: var(--muted); font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
    .inventory-chips { display: flex; flex-wrap: wrap; gap: 7px; }
    .inventory-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      max-width: 100%;
      padding: 7px 9px;
      border: 1px solid #345470;
      border-radius: 999px;
      background: #102033;
      color: #eaf3fb;
      font-size: 13px;
      font-weight: 750;
    }
    .inventory-chip.collection { border-color:#8bb8ff; background:#122747; color:#d9e8ff; }
    .inventory-chip.permanent { border-color:#69c18a; background:#112b24; color:#d8ffe6; }
    .inventory-chip.paid { border-color:#f0c66d; background:#302312; color:#ffe7aa; }
    .inventory-chip.tickets { border-color:#d99cff; background:#28173b; color:#f4dcff; }
    .achievement-showcase { display: grid; gap: 8px; margin-top: 10px; }
    .achievement-card {
      padding: 10px 11px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel);
    }
    .achievement-card b { display:block; }
    .achievement-rarity { margin-top: 4px; font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: .04em; }
    .achievement-card.common { border-color:#6f8798; background:#152537; }
    .achievement-card.rare { border-color:#56b37a; background:#102c24; color:#eaffef; }
    .achievement-card.epic { border-color:#9a75ff; background:#241840; color:#f0e9ff; }
    .achievement-card.legendary { border-color:#e2ad42; background:#31230d; color:#fff0c4; }
    .achievement-card.mythic { border-color:#ff6e9d; background:linear-gradient(135deg,#3c1225,#23143d); color:#ffe4ef; box-shadow:0 0 18px #ff6e9d22; }
    .radio-player { width: 100%; margin-top: 10px; }
    .persistent-radio {
      position: fixed;
      left: 16px;
      right: 16px;
      bottom: max(12px, env(safe-area-inset-bottom));
      z-index: 80;
      display: none;
      width: min(calc(100% - 32px), 528px);
      margin: 0 auto;
      border-radius: 999px;
      background: #111;
      box-shadow: 0 8px 28px #0009;
    }
    .persistent-radio.active { display: block; }
    .radio-list { display: grid; gap: 8px; margin-top: 12px; }
    .radio-row { display: grid; grid-template-columns: minmax(0, 1fr) 44px; gap: 8px; }
    .radio-row .btn { min-height: 42px; margin: 0; text-align: left; }
    .radio-row .favorite-btn { padding: 8px; text-align: center; }
    .shift-card .shift-options { display:grid; gap:8px; margin-top:10px; }
    .shift-card .shift-options .btn { margin-top:0; min-height:44px; }
    .btn {
      width: 100%;
      min-height: 50px;
      margin-top: 12px;
      padding: 12px 14px;
      border: 0;
      border-radius: var(--button-radius);
      background: var(--accent);
      color: white;
      font-weight: 750;
      cursor: pointer;
    }
    .btn.secondary { background: var(--panel-2); }
    .btn:disabled { opacity: .45; cursor: default; }
    .theme-switcher { display:grid; gap:8px; margin-top:14px; }
    .theme-platform-switch {
      position: relative;
      width: min(100%, 330px);
      margin: 0 auto;
      padding-top: 62px;
    }
    .theme-platform-switch input {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }
    .theme-switch-icons,
    .theme-switch-labels {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      text-align: center;
    }
    .theme-switch-icons {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      align-items: end;
    }
    .theme-platform-icon {
      display: grid;
      place-items: center;
      height: 48px;
      color: var(--muted);
      opacity: .58;
      transition: .25s ease;
      cursor: pointer;
    }
    .theme-platform-icon svg {
      width: 34px;
      height: 34px;
      fill: currentColor;
      filter: drop-shadow(0 1px 0 rgba(255,255,255,.22));
    }
    .theme-switch-track {
      position: relative;
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      height: 30px;
      overflow: hidden;
      border: 1px solid color-mix(in srgb, var(--line) 72%, #ffffff);
      border-radius: 999px;
      background:
        linear-gradient(to bottom, #fdfdfd 0%, #d7d7d7 42%, #a9a9a9 50%, #f5f5f5 60%, #dddddd 100%);
      box-shadow:
        0 5px 12px rgba(0,0,0,.32),
        inset 0 1px 2px rgba(255,255,255,.95),
        inset 0 -1px 1px rgba(0,0,0,.2);
    }
    .theme-switch-track label {
      position: relative;
      z-index: 2;
      cursor: pointer;
    }
    .theme-switch-track label + label { border-left: 1px solid rgba(50,50,50,.72); }
    .theme-switch-knob {
      position: absolute;
      top: 3px;
      left: 3px;
      width: calc(50% - 6px);
      height: 22px;
      border: 1px solid #777;
      border-radius: 999px;
      background:
        linear-gradient(to bottom, #ffffff 0%, #f3f3f3 42%, #b6b6b6 51%, #fbfbfb 61%, #dedede 100%);
      box-shadow:
        0 2px 3px rgba(0,0,0,.3),
        inset 0 1px 1px rgba(255,255,255,.95);
      transition: transform .28s cubic-bezier(.22,.8,.3,1);
    }
    .theme-switch-knob::after {
      content: "";
      position: absolute;
      left: 14px;
      right: 14px;
      bottom: -2px;
      height: 2px;
      border-radius: 2px;
      background: #c2008f;
      box-shadow: 0 0 5px rgba(194,0,143,.55);
    }
    .theme-switch-labels {
      margin-top: 11px;
      color: var(--muted);
      font-size: 16px;
      font-weight: 850;
    }
    .theme-switch-labels label {
      cursor: pointer;
      transition: .25s ease;
    }
    #themeApple:checked ~ .theme-switch-track .theme-switch-knob { transform: translateX(0); }
    #themeExpressive:checked ~ .theme-switch-track .theme-switch-knob { transform: translateX(calc(100% + 6px)); }
    #themeApple:checked ~ .theme-switch-icons .theme-apple-icon,
    #themeApple:checked ~ .theme-switch-labels .theme-apple-label,
    #themeExpressive:checked ~ .theme-switch-icons .theme-expressive-icon,
    #themeExpressive:checked ~ .theme-switch-labels .theme-expressive-label {
      color: var(--text);
      opacity: 1;
    }
    .theme-platform-switch:focus-within .theme-switch-track {
      outline: 3px solid color-mix(in srgb, var(--accent) 24%, transparent);
      outline-offset: 4px;
    }
    .depth { padding: 18px 0; text-align: center; font-size: 48px; font-weight: 850; }
    .meter { height: 12px; overflow: hidden; border-radius: 7px; background: #09111c; }
    .fill { height: 100%; background: var(--accent); transition: width .25s ease; }
    .notice { white-space: pre-line; border-color: #4b6f91; }
    .section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .counter { white-space: nowrap; font-weight: 800; }
    .mine-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin-top: 12px; }
    .mine-cell {
      min-height: 56px;
      border: 1px solid #50708d;
      border-radius: 14px;
      background: linear-gradient(145deg, #263d55, #102132);
      color: var(--text);
      font-size: 23px;
      font-weight: 850;
      box-shadow: inset 0 2px 2px #ffffff1c, 0 5px 9px #02060b60;
    }
    .mine-cell.used { opacity: .45; filter: grayscale(.4); }
    .tool-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 12px; }
    .small-btn { padding: 10px 12px; font-size: 14px; }
    .btn.danger { background: linear-gradient(135deg, #7b3b2f, #4b2230); }
    .ticket-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin-top: 12px; }
    .ticket-cell, .super-cell {
      position: relative;
      display: grid;
      place-items: center;
      perspective: 160px;
      aspect-ratio: 1;
      min-width: 0;
      border: 1px solid #50708d;
      border-radius: 8px;
      background: linear-gradient(145deg, #2d4b65, #132638);
      box-shadow: inset 0 2px 2px #ffffff1c, 0 5px 9px #02060b80;
      color: white;
      cursor: pointer;
      overflow: hidden;
    }
    .ticket-cell .hammer, .super-cell .hammer {
      position: absolute;
      z-index: 4;
      opacity: 0;
      font-size: 34px;
      transform: translate(30%, -45%) rotate(-35deg);
    }
    .breaking .hammer { animation: hammer .55s ease-in-out; }
    .breaking .cat-figure { animation: crack .55s ease-in-out; }
    .cat-figure {
      display: block;
      width: 66%;
      height: 66%;
      transform: rotateX(8deg) rotateY(-7deg);
      filter: drop-shadow(0 8px 4px #0008);
    }
    .cat-figure .cat-head { fill: var(--cat-main); stroke: var(--cat-outline); stroke-width: 5; stroke-linejoin: round; }
    .cat-figure .cat-muzzle { fill: var(--cat-muzzle); }
    .cat-figure .cat-inner-ear { fill: var(--cat-ear); }
    .cat-figure .cat-stripe { fill: none; stroke: var(--cat-stripe); stroke-width: 5; stroke-linecap: round; }
    .cat-figure .cat-eye { fill: var(--cat-eye, #d9f173); stroke: #172313; stroke-width: 3; }
    .cat-figure .cat-pupil { fill: #13200f; }
    .cat-figure .cat-nose { fill: #e88b96; }
    .cat-figure .cat-whiskers { stroke: #fff7e6; stroke-width: 3; stroke-linecap: round; opacity: .92; }
    .cat-ginger { --cat-main:#df9a4f; --cat-outline:#6e3b1e; --cat-muzzle:#ffe0aa; --cat-ear:#f3a6ae; --cat-stripe:#8d4b25; }
    .cat-tabby { --cat-main:#9b806a; --cat-outline:#493a31; --cat-muzzle:#e6d1b7; --cat-ear:#e7a6aa; --cat-stripe:#53443b; }
    .cat-black { --cat-main:#3e4851; --cat-outline:#172129; --cat-muzzle:#d0d7d7; --cat-ear:#c98f9d; --cat-stripe:#71808a; }
    .cat-cream { --cat-main:#e6c47c; --cat-outline:#765d30; --cat-muzzle:#fff0c9; --cat-ear:#efabb0; --cat-stripe:#b48743; }
    .cat-white { --cat-main:#f4eee2; --cat-outline:#8f8270; --cat-muzzle:#ffffff; --cat-ear:#e7a7b2; --cat-stripe:#c7bda8; --cat-eye:#87d96d; }
    .cat-blue { --cat-main:#6d7f91; --cat-outline:#273746; --cat-muzzle:#d6e0e5; --cat-ear:#c58b9d; --cat-stripe:#435463; --cat-eye:#d7f06e; }
    .cat-calico { --cat-main:#f0c16b; --cat-outline:#56382a; --cat-muzzle:#fff0cf; --cat-ear:#e9a1aa; --cat-stripe:#252930; --cat-eye:#9feb78; }
    .cat-tuxedo { --cat-main:#222830; --cat-outline:#0e151c; --cat-muzzle:#f2efe4; --cat-ear:#b97889; --cat-stripe:#f2efe4; --cat-eye:#bff06e; }
    .cat-rust { --cat-main:#b85d42; --cat-outline:#4d251d; --cat-muzzle:#f5c79b; --cat-ear:#dc8d91; --cat-stripe:#5b2c22; --cat-eye:#c8f36d; }
    .super-cell .cat-figure { width: 83%; height: 83%; }
    .cell-prize {
      display: grid;
      place-items: center;
      position: absolute;
      inset: 8px;
      z-index: 5;
      border-radius: 8px;
      background: radial-gradient(circle, #ffe28b, #d19531 65%, #7b481c);
      color: #201307;
      font-weight: 900;
      text-align: center;
      animation: prize-reveal .65s cubic-bezier(.2,.85,.25,1.25);
    }
    .super-cell .cell-prize { inset: 2px; border-radius: 4px; font-size: 9px; }
    .opened { background: #101c28; color: var(--ok); cursor: default; }
    @keyframes hammer {
      0% { opacity: 0; transform: translate(45%, -65%) rotate(-45deg); }
      35% { opacity: 1; }
      75% { opacity: 1; transform: translate(0, 0) rotate(18deg); }
      100% { opacity: 0; }
    }
    @keyframes crack {
      0%, 60% { transform: scale(1); }
      80% { transform: scale(.72) rotate(-9deg); filter: brightness(1.8); }
      100% { transform: scale(.12) rotate(16deg); opacity: 0; }
    }
    @keyframes prize-reveal {
      from { opacity: 0; transform: scale(.2) rotateY(80deg); }
      to { opacity: 1; transform: scale(1) rotateY(0); }
    }
    .super-grid { display: grid; grid-template-columns: repeat(9, minmax(0, 1fr)); gap: 4px; margin-top: 12px; }
    .super-cell { border-radius: 5px; font-size: 17px; }
    .super-cell .cat { font-size: clamp(15px, 5vw, 23px); }
    .super-cell .hammer { font-size: 22px; }
    .game-result {
      min-height: 1.35em;
      margin-top: 10px;
      color: var(--ok);
      font-weight: 700;
    }
    .bag-screen { margin-top: 14px; }
    .bag-summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 15px 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .bag-summary h2 { margin: 0; font-size: 22px; }
    .bag-balance { color: #ffd37d; font-size: 18px; font-weight: 800; white-space: nowrap; }
    .bag-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
    .bag-actions .btn { min-height: 44px; margin: 0; }
    .inventory { display: grid; gap: 8px; margin-top: 12px; }
    .inventory-group {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .inventory-group summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-height: 48px;
      padding: 11px 14px;
      cursor: pointer;
      font-weight: 800;
      list-style: none;
    }
    .inventory-group summary::-webkit-details-marker { display: none; }
    .inventory-group summary::after { content: "⌄"; color: var(--muted); font-size: 20px; }
    .inventory-group[open] summary::after { transform: rotate(180deg); }
    .inventory-group-count { color: var(--muted); font-size: 13px; font-weight: 600; }
    .inventory-list { padding: 0 14px 5px; border-top: 1px solid var(--line); }
    .inventory-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 42px;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }
    .inventory-row:last-child { border-bottom: 0; }
    .inventory-row-main {
      display: flex;
      min-width: 0;
      flex-direction: column;
      gap: 6px;
    }
    .inventory-row-main span {
      overflow-wrap: anywhere;
    }
    .inventory-row b { flex: 0 0 auto; color: #dbe7f2; }
    .inventory-use {
      min-height: 30px;
      width: fit-content;
      margin: 0;
      padding: 6px 10px;
      border-radius: 8px;
      font-size: 12px;
    }
    .shop-screen {
      min-height: calc(100vh - 112px);
      margin-top: 14px;
      overflow: hidden;
      border: 1px solid #604224;
      border-radius: 8px;
      background: #100d0b;
    }
    .shop-hero {
      position: relative;
      display: flex;
      min-height: 176px;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      padding: 18px;
      background:
        linear-gradient(180deg, #0806041a 15%, #100d0bf2 100%),
        url("/miniapp/shop-bg.png") center 28% / cover;
    }
    .shop-hero-copy { position: relative; z-index: 1; max-width: 68%; }
    .shop-kicker { margin-bottom: 4px; color: #f2c987; font-size: 13px; font-weight: 800; text-transform: uppercase; }
    .shop-hero h2 { margin: 0; font-size: 25px; }
    .shop-hero p { margin: 5px 0 0; color: #e1d5c7; font-size: 14px; line-height: 1.35; }
    .shop-coins {
      position: relative;
      z-index: 1;
      padding: 8px 10px;
      border: 1px solid #d49a50;
      border-radius: 8px;
      background: #15100cef;
      font-weight: 800;
      white-space: nowrap;
    }
    .shop-toolbar {
      position: sticky;
      top: 0;
      z-index: 5;
      padding: 10px 12px;
      border-bottom: 1px solid #48321f;
      background: #100d0bf7;
    }
    .shop-tabs {
      display: flex;
      gap: 7px;
      overflow-x: auto;
      padding-bottom: 4px;
      scrollbar-width: thin;
      scrollbar-color: #c98e49 #211811;
      scroll-snap-type: x proximity;
    }
    .shop-tabs::-webkit-scrollbar { height: 6px; }
    .shop-tabs::-webkit-scrollbar-track { background: #211811; border-radius: 999px; }
    .shop-tabs::-webkit-scrollbar-thumb { background: #c98e49; border-radius: 999px; }
    .shop-tab {
      flex: 0 0 auto;
      min-height: 38px;
      padding: 8px 12px;
      border: 1px solid #c98e49;
      border-radius: 8px;
      background: #211811;
      color: white;
      font-weight: 700;
      scroll-snap-align: start;
    }
    .shop-tab.active { background: #a9652d; }
    .shop-products { padding: 0 14px; }
    .product {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 6px 12px;
      padding: 14px 0;
      border-bottom: 1px solid #48321f;
    }
    .product:last-child { border-bottom: 0; }
    .product-name { min-width: 0; font-weight: 800; }
    .price { color: #ffd37d; font-weight: 800; white-space: nowrap; }
    .description {
      grid-column: 1 / -1;
      display: -webkit-box;
      overflow: hidden;
      color: #d0c6bb;
      font-size: 14px;
      line-height: 1.4;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 3;
    }
    .product-meta { min-width: 0; align-self: center; }
    .product-meta .muted { font-size: 13px; }
    .owned { color: var(--ok); font-size: 13px; }
    .shop-buy {
      width: auto;
      min-height: 38px;
      margin: 0;
      padding: 8px 13px;
      align-self: end;
      background: #b66c2c;
      font-size: 14px;
      white-space: nowrap;
    }
    .shop-back { padding: 0 14px 14px; }
    @media (max-width: 390px) {
      .shop-hero { min-height: 154px; padding: 14px; }
      .shop-hero-copy { max-width: 64%; }
      .shop-hero h2 { font-size: 22px; }
      .shop-coins { padding: 7px 8px; font-size: 14px; }
      .product { grid-template-columns: minmax(0, 1fr) auto; gap: 5px 8px; }
      .shop-buy { padding-inline: 10px; }
    }
    .error { border-color: var(--danger); color: #ffd8da; }
    .dig-animation {
      position: fixed;
      inset: 0;
      z-index: 100;
      display: grid;
      place-items: center;
      background: #07101be8;
      backdrop-filter: blur(4px);
    }
    .dig-scene {
      position: relative;
      width: min(78vw, 330px);
      aspect-ratio: 1;
      overflow: hidden;
      border: 1px solid #765638;
      border-radius: 50%;
      background: radial-gradient(circle at 50% 38%, #594531 0 14%, #2e241c 38%, #100d0b 72%);
      box-shadow: inset 0 0 55px #000, 0 18px 45px #000b;
    }
    .dig-pickaxe {
      position: absolute;
      left: 45%;
      top: 17%;
      z-index: 3;
      font-size: 88px;
      transform-origin: 18% 82%;
      animation: pickaxe-swing .52s ease-in-out infinite;
    }
    .dig-rock {
      position: absolute;
      z-index: 2;
      width: 22px;
      height: 17px;
      border-radius: 45%;
      background: #a27b52;
      box-shadow: inset -5px -5px 5px #543b27;
      animation: rock-fall .8s ease-out infinite;
    }
    .dig-rock.r1 { left: 26%; top: 58%; }
    .dig-rock.r2 { left: 58%; top: 64%; animation-delay: .18s; }
    .dig-rock.r3 { left: 45%; top: 49%; animation-delay: .35s; }
    .dig-caption {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 20%;
      z-index: 5;
      text-align: center;
      font-size: 23px;
      font-weight: 850;
      text-shadow: 0 2px 5px #000;
    }
    .chest {
      overflow: hidden;
      border-color: #e3ac45;
      background: radial-gradient(circle at 50% 0, #725620, var(--panel) 65%);
      animation: chest-glow .8s ease-out;
    }
    .treasure-chest {
      position: relative;
      width: 156px;
      height: 122px;
      margin: 0 auto 18px;
      filter: drop-shadow(0 17px 10px #0009);
    }
    .treasure-chest::before {
      content: "";
      position: absolute;
      left: 12px;
      right: 12px;
      top: 39px;
      height: 52px;
      border-radius: 50%;
      background: radial-gradient(circle, #fff9c7 0 18%, #ffd543 42%, #ff9b17 67%, transparent 72%);
      filter: blur(9px);
      opacity: 0;
      animation: treasure-light 1s .28s ease-out forwards;
    }
    .treasure-chest::after {
      content: "";
      position: absolute;
      left: 17px;
      right: 17px;
      bottom: -8px;
      height: 18px;
      border-radius: 50%;
      background: #0009;
      filter: blur(8px);
    }
    .chest-light {
      position: absolute;
      z-index: 1;
      left: -17px;
      right: -17px;
      top: 30px;
      height: 58px;
      background:
        radial-gradient(circle at 48% 55%, #fff 0 10%, #ffe16a 25%, transparent 53%),
        linear-gradient(90deg, transparent, #ffe16a99 47%, #fff8c8 50%, #ffe16a99 53%, transparent);
      filter: blur(4px);
      opacity: 0;
      transform: scaleX(.6);
      animation: treasure-beam 1.1s .38s ease-out forwards;
    }
    .chest-shine {
      position: absolute;
      z-index: 5;
      left: 50%;
      top: 36px;
      width: 9px;
      height: 74px;
      border-radius: 50%;
      background: linear-gradient(#fffdf0, #ffe36c 45%, transparent);
      box-shadow:
        -38px 11px 0 -3px #ffd75a,
        34px 7px 0 -4px #fff6b8,
        0 0 22px 8px #fff09c;
      opacity: 0;
      transform: translateX(-50%) rotate(90deg) scale(.35);
      animation: chest-spark .95s .45s ease-out forwards;
    }
    .chest-base, .chest-lid {
      position: absolute;
      left: 18px;
      width: 120px;
      border: 4px solid #f6d06a;
      background:
        linear-gradient(90deg, #f4c95d 0 8px, transparent 8px calc(100% - 8px), #f4c95d calc(100% - 8px)),
        repeating-linear-gradient(0deg, #8a4b23 0 10px, #b46b2f 10px 15px, #7d401e 15px 25px);
      box-shadow:
        inset 0 0 0 2px #693716,
        inset 0 12px 12px #ffcf6240,
        0 4px 0 #5a2f15;
    }
    .chest-base {
      bottom: 3px;
      z-index: 3;
      height: 55px;
      border-radius: 7px 7px 13px 13px;
    }
    .chest-base::before, .chest-lid::before {
      content: "";
      position: absolute;
      inset: 5px 0 auto;
      height: 7px;
      background:
        radial-gradient(circle, #fff2a9 0 2px, #b87a22 2px 4px, transparent 4px) 0 0 / 16px 7px repeat-x,
        linear-gradient(#ffd66e, #b47721);
    }
    .chest-base::after {
      content: "";
      position: absolute;
      left: 49px;
      top: 17px;
      width: 22px;
      height: 29px;
      border-radius: 8px 8px 10px 10px;
      background: linear-gradient(#ffdf74, #bd7b22);
      border: 3px solid #6b3a16;
      box-shadow: 0 -16px 0 -8px #f6d06a;
    }
    .chest-lid {
      top: 11px;
      z-index: 2;
      height: 46px;
      border-radius: 46px 46px 6px 6px;
      transform-origin: 50% 100%;
      animation: chest-open .9s cubic-bezier(.25,.8,.25,1) forwards;
    }
    .chest-lid::after {
      content: "";
      position: absolute;
      left: 55px;
      top: 2px;
      width: 12px;
      height: 48px;
      border-radius: 8px;
      background: linear-gradient(#fff0a8, #c18328);
      box-shadow: 0 0 0 2px #77410f;
    }
    @keyframes pickaxe-swing {
      0% { transform: rotate(-42deg) translate(-8px, -8px); }
      55% { transform: rotate(21deg) translate(4px, 10px); }
      100% { transform: rotate(-42deg) translate(-8px, -8px); }
    }
    @keyframes rock-fall {
      0% { opacity: 0; transform: translate(0, -18px) rotate(0); }
      35% { opacity: 1; }
      100% { opacity: 0; transform: translate(34px, 48px) rotate(150deg); }
    }
    @keyframes chest-open {
      0% { transform: translateY(0) rotateX(0); }
      65%, 100% { transform: translateY(-31px) rotateX(63deg); }
    }
    @keyframes treasure-light {
      to { opacity: .96; transform: scale(1.45); }
    }
    @keyframes treasure-beam {
      to { opacity: .94; transform: scaleX(1); }
    }
    @keyframes chest-spark {
      0% { opacity: 0; transform: translateX(-50%) rotate(90deg) scale(.2); }
      45% { opacity: 1; }
      100% { opacity: 0; transform: translateX(-50%) rotate(90deg) scale(1.15); }
    }
    @keyframes chest-glow {
      45% { box-shadow: 0 0 35px #f8c34c99; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation: none !important; transition: none !important; }
    }
  </style>
</head>
<body>
<div class="app-bg" aria-hidden="true"></div>
<main>
  <header class="top">
    <div>
      <h1 id="screen-title">⛏️ Шахта</h1>
      <div id="name" class="muted">Загрузка...</div>
    </div>
    <div class="top-actions">
      <button class="top-profile" onclick="handleTopProfileButton()">Профиль</button>
    </div>
  </header>
  <div id="content"></div>
</main>
<audio id="radioPlayer" class="persistent-radio" controls preload="none"></audio>
<script>
  const telegram = window.Telegram && window.Telegram.WebApp;
  const content = document.getElementById("content");
  const nameNode = document.getElementById("name");
  const screenTitle = document.getElementById("screen-title");
  const topProfileButton = document.querySelector(".top-profile");
  const radioPlayer = document.getElementById("radioPlayer");
  let state = null;
  let busy = false;
  let shopCategory = "";
  let activeView = "mine";
  let profileReturnView = "mine";
  let currentProfile = null;

  radioPlayer.addEventListener("play", () => {
    radioPlayer.classList.add("active");
    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "playing";
  });
  radioPlayer.addEventListener("pause", () => {
    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "paused";
  });
  radioPlayer.addEventListener("ended", () => {
    radioPlayer.classList.remove("active");
    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "none";
  });

  function setScreenHeader(view) {
    activeView = view;
    document.body.dataset.view = view;
    if (view === "shop") {
      screenTitle.textContent = "🛒 Магазин";
      nameNode.textContent = "Лавка шахтёра";
    } else if (view === "bag") {
      screenTitle.textContent = "🎒 Сумка";
      nameNode.textContent = "Инвентарь шахтёра";
    } else if (view === "profile") {
      screenTitle.textContent = "👤 Профиль";
      nameNode.textContent = "Информация игрока";
    } else if (view === "mineAdmin") {
      screenTitle.textContent = "⛏️ Панель шахты";
      nameNode.textContent = "Управление и просмотр";
    } else if (view === "adminPanel") {
      screenTitle.textContent = "🛡️ Админ";
      nameNode.textContent = "Панель управления";
    } else if (view === "weather") {
      screenTitle.textContent = "🌦️ Погода";
      nameNode.textContent = "Город и текущая сводка";
    } else if (view === "radio") {
      screenTitle.textContent = "📻 Радио";
      nameNode.textContent = "Поиск станций и избранное";
    } else {
      screenTitle.textContent = "⛏️ Шахта";
      nameNode.textContent = state && state.registered ? state.name : "Новая вылазка";
    }
    updateTopProfileButton();
  }

  function updateTopProfileButton() {
    if (!topProfileButton) return;
    topProfileButton.textContent = activeView === "profile" ? "Назад" : "Профиль";
  }

  function handleTopProfileButton() {
    if (activeView === "profile") {
      returnFromProfile();
    } else {
      showProfile();
    }
  }

  function returnFromProfile() {
    const target = profileReturnView || "mine";
    if (target === "shop") return showShop(shopCategory);
    if (target === "bag") return showBag();
    if (target === "weather") return showWeather();
    if (target === "radio") return showRadio();
    if (target === "mineAdmin") return showMineAdmin();
    return renderMine();
  }

  function scrollToTop() {
    window.scrollTo(0, 0);
  }

  function enableHorizontalWheelScroll(selector) {
    const node = document.querySelector(selector);
    if (!node || node.dataset.wheelScrollBound === "1") return;
    node.dataset.wheelScrollBound = "1";
    node.addEventListener("wheel", event => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX) || node.scrollWidth <= node.clientWidth) return;
      event.preventDefault();
      node.scrollLeft += event.deltaY;
    }, { passive: false });
  }

  if (telegram) {
    telegram.ready();
    telegram.expand();
  }

  const headers = () => ({
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": telegram ? telegram.initData : ""
  });

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { ...headers(), ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({ detail: "Сервер вернул неверный ответ." }));
    if (!response.ok) throw new Error(data.detail || "Ошибка запроса.");
    return data;
  }

  async function apiForm(path, formData) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "X-Telegram-Init-Data": telegram ? telegram.initData : "" },
      body: formData
    });
    const data = await response.json().catch(() => ({ detail: "Сервер вернул неверный ответ." }));
    if (!response.ok) throw new Error(data.detail || "Ошибка запроса.");
    return data;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function escapeJs(value) {
    return String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  }

  function jsAttrString(value) {
    return JSON.stringify(String(value ?? ""))
      .replace(/&/g, "\\u0026")
      .replace(/</g, "\\u003c")
      .replace(/>/g, "\\u003e")
      .replace(/"/g, "&quot;");
  }

  function plainText(value) {
    const template = document.createElement("template");
    template.innerHTML = String(value ?? "").replace(/<br\s*\/?>/gi, "\n");
    return (template.content.textContent || "").trim();
  }

  function showError(error) {
    content.innerHTML = `<section class="panel error">${escapeHtml(plainText(error.message || error))}</section>`;
  }

  function showNotice(text, special = false) {
    const node = document.createElement("section");
    node.className = `panel notice${special ? " chest" : ""}`;
    const cleanText = plainText(text);
    if (special) {
      node.innerHTML = `
        <div class="treasure-chest" aria-hidden="true">
          <span class="chest-light"></span>
          <span class="chest-shine"></span>
          <span class="chest-base"></span>
          <span class="chest-lid"></span>
        </div>
        <div>${escapeHtml(cleanText)}</div>`;
    } else {
      node.textContent = cleanText;
    }
    content.prepend(node);
  }

  function catFigure(index = 0) {
    const coats = [
      "cat-ginger", "cat-tabby", "cat-black", "cat-cream", "cat-white",
      "cat-blue", "cat-calico", "cat-tuxedo", "cat-rust"
    ];
    const coat = coats[Math.abs(index) % coats.length];
    return `<svg class="cat-figure ${coat}" viewBox="0 0 100 100" role="img" aria-label="Котик">
      <path class="cat-head" d="M18 43 15 15 39 29Q50 22 61 29L85 15 82 43Q90 55 85 73 80 91 50 93 20 91 15 73 10 55 18 43Z"/>
      <path class="cat-inner-ear" d="M22 25 24 40 35 32Z"/>
      <path class="cat-inner-ear" d="M78 25 76 40 65 32Z"/>
      <path class="cat-stripe" d="M42 31 47 41M50 29v12M58 31 53 41M24 49l10 4M76 49l-10 4"/>
      <ellipse class="cat-eye" cx="35" cy="54" rx="8" ry="10"/>
      <ellipse class="cat-eye" cx="65" cy="54" rx="8" ry="10"/>
      <path class="cat-pupil" d="M35 47v14M65 47v14" stroke-linecap="round" stroke-width="3"/>
      <path class="cat-muzzle" d="M31 67Q39 62 50 70 61 62 69 67 71 82 50 83 29 82 31 67Z"/>
      <path class="cat-nose" d="M45 67Q50 63 55 67L50 73Z"/>
      <path d="M50 73q-5 6-10 2M50 73q5 6 10 2" fill="none" stroke="#4b3434" stroke-width="2.5" stroke-linecap="round"/>
      <path class="cat-whiskers" d="M37 72 10 66M37 77 9 79M63 72 90 66M63 77 91 79"/>
    </svg>`;
  }

  function catForCell(index, width = 9) {
    const row = Math.floor(index / width);
    const column = index % width;
    return (index * 7 + row * 5 + column * 3 + 11) % 9;
  }

  function showDigAnimation() {
    const overlay = document.createElement("div");
    overlay.className = "dig-animation";
    overlay.innerHTML = `<div class="dig-scene">
      <span class="dig-pickaxe">⛏️</span>
      <span class="dig-rock r1"></span>
      <span class="dig-rock r2"></span>
      <span class="dig-rock r3"></span>
      <div class="dig-caption">Копаем метр...</div>
    </div>`;
    document.body.append(overlay);
    return overlay;
  }

  function normalizeStartParam(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "shop" || normalized.startsWith("shop_")) return "shop";
    if (normalized === "bag" || normalized.startsWith("bag_")) return "bag";
    if (normalized === "profile" || normalized.startsWith("profile_")) return "profile";
    if (normalized === "weather" || normalized.startsWith("weather_")) return "weather";
    if (normalized === "radio" || normalized.startsWith("radio_")) return "radio";
    if (normalized === "mine" || normalized.startsWith("mine_")) return "mine";
    return normalized;
  }

  function readRawStartParam() {
    const query = new URLSearchParams(location.search);
    const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
    const urlParam =
      query.get("tgWebAppStartParam") ||
      hash.get("tgWebAppStartParam") ||
      query.get("start_param") ||
      hash.get("start_param") ||
      query.get("startapp") ||
      hash.get("startapp") ||
      query.get("view") ||
      hash.get("view");
    if (urlParam) return String(urlParam).trim().toLowerCase();

    const encodedInitData = query.get("tgWebAppData") || hash.get("tgWebAppData");
    if (encodedInitData) {
      try {
        const nestedParam = new URLSearchParams(decodeURIComponent(encodedInitData)).get("start_param");
        if (nestedParam) return String(nestedParam).trim().toLowerCase();
      } catch (_) {
        // Fall through to Telegram's parsed launch data.
      }
    }

    const direct =
      (telegram && telegram.initDataUnsafe && telegram.initDataUnsafe.start_param) ||
      (telegram && telegram.initData && new URLSearchParams(telegram.initData).get("start_param"));
    return String(direct || "").trim().toLowerCase();
  }

  function readStartParam() {
    return normalizeStartParam(readRawStartParam());
  }

  function readStartOwner() {
    const match = readRawStartParam().match(/^(?:mine|shop|bag|profile|weather|radio)_(\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function isCoolingDown() {
    return state && state.cooldownUntil &&
      new Date(state.cooldownUntil).getTime() > Date.now() &&
      !state.inSession;
  }

  function rankEmblem(level) {
    return ["", "⛏️", "🛠️", "👑", "🏔️"][Number(level) || 0] || "⛏️";
  }

  function rankCosmeticHtml(compact = false) {
    const rank = state && state.rank ? state.rank : {};
    if (!rank.level) return "";
    const discount = rank.level * 5;
    const text = compact
      ? `Рамка, эмблема и значок сумки активны. Скидка ${discount}%.`
      : `Косметика активна: эмблема ранга, цветная рамка карточки и уникальный значок в сумке. Скидка ${discount}% на припасы и особое снаряжение.`;
    return `<section class="panel rank-card rank-${rank.level}">
      <div class="rank-line"><span class="rank-emblem">${rankEmblem(rank.level)}</span><span>${escapeHtml(rank.name)}</span></div>
      <div class="muted" style="margin-top:7px">${escapeHtml(text)}</div>
    </section>`;
  }

  function utilityActionsHtml() {
    return `<div class="utility-actions">
      <button class="btn secondary" onclick="showWeather()">Погода</button>
      <button class="btn secondary" onclick="showRadio()">Радио</button>
    </div>`;
  }

  function loadMiniSettings() {
    try {
      return JSON.parse(localStorage.getItem("miniAppSettings") || "{}");
    } catch (_) {
      return {};
    }
  }

  function saveMiniSettings(settings) {
    localStorage.setItem("miniAppSettings", JSON.stringify(settings));
  }

  const MINI_APP_THEMES = {
    expressive: "Material 3 Expressive",
    glass: "Liquid Glass",
  };

  function currentMiniTheme() {
    const theme = loadMiniSettings().theme || "expressive";
    return Object.prototype.hasOwnProperty.call(MINI_APP_THEMES, theme) ? theme : "expressive";
  }

  function applyMiniTheme(theme) {
    const safeTheme = Object.prototype.hasOwnProperty.call(MINI_APP_THEMES, theme) ? theme : "expressive";
    document.documentElement.dataset.theme = safeTheme;
    document.documentElement.style.colorScheme = "dark";
    document.body.dataset.theme = safeTheme;
  }

  function enforceMiniAppTheme() {
    applyMiniTheme(currentMiniTheme());
  }

  function setMiniTheme(theme) {
    const settings = loadMiniSettings();
    settings.theme = Object.prototype.hasOwnProperty.call(MINI_APP_THEMES, theme) ? theme : "expressive";
    saveMiniSettings(settings);
    enforceMiniAppTheme();
    const block = document.getElementById("themeSwitcher");
    if (block) block.outerHTML = themeSwitcherHtml();
  }

  function themeSwitcherHtml() {
    const theme = currentMiniTheme();
    return `<div id="themeSwitcher" class="theme-switcher">
      <div class="muted">Тема интерфейса</div>
      <div class="theme-platform-switch">
        <input type="radio" name="miniAppTheme" id="themeApple" value="glass" ${theme === "glass" ? "checked" : ""} onchange="setMiniTheme('glass')">
        <input type="radio" name="miniAppTheme" id="themeExpressive" value="expressive" ${theme === "expressive" ? "checked" : ""} onchange="setMiniTheme('expressive')">
        <div class="theme-switch-icons">
          <label class="theme-platform-icon theme-apple-icon" for="themeApple" aria-label="Liquid Glass">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M17.2 12.5c0-2.5 2.1-3.7 2.2-3.8-1.2-1.8-3.1-2-3.8-2-1.6-.2-3.1.9-3.9.9-.8 0-2-.9-3.3-.9-1.7 0-3.2 1-4.1 2.4-1.8 3-.5 7.5 1.3 10 .9 1.2 1.9 2.6 3.3 2.5 1.3-.1 1.8-.8 3.4-.8 1.6 0 2 .8 3.4.8 1.4 0 2.3-1.2 3.1-2.5 1-1.4 1.4-2.8 1.4-2.9-.1 0-3-.9-3-3.7zM14.6 5c.7-.8 1.2-2 1.1-3.1-1 .1-2.2.7-2.9 1.5-.6.7-1.2 1.9-1.1 3 1.1.1 2.2-.6 2.9-1.4z"/>
            </svg>
          </label>
          <label class="theme-platform-icon theme-expressive-icon" for="themeExpressive" aria-label="Material 3 Expressive">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2.4l1.8 5.2 5.5.2-4.4 3.3 1.5 5.3L12 13.3l-4.5 3.1 1.5-5.3-4.4-3.3 5.5-.2L12 2.4zm6.5 12.6l.8 2.3 2.4.1-1.9 1.4.7 2.3-2-1.3-2 1.3.7-2.3-1.9-1.4 2.4-.1.8-2.3zM4.7 15l.8 2.3 2.4.1L6 18.8l.7 2.3-2-1.3-2 1.3.7-2.3-1.9-1.4 2.4-.1.8-2.3z"/>
            </svg>
          </label>
        </div>
        <div class="theme-switch-track">
          <span class="theme-switch-knob"></span>
          <label for="themeApple"></label>
          <label for="themeExpressive"></label>
        </div>
        <div class="theme-switch-labels">
          <label class="theme-apple-label" for="themeApple">Liquid Glass</label>
          <label class="theme-expressive-label" for="themeExpressive">M3 Expressive</label>
        </div>
      </div>
    </div>`;
  }

  enforceMiniAppTheme();
  if (telegram && typeof telegram.onEvent === "function") {
    telegram.onEvent("themeChanged", enforceMiniAppTheme);
  }
  new MutationObserver(() => {
    if (document.body.dataset.theme !== currentMiniTheme()) enforceMiniAppTheme();
  }).observe(document.body, { attributes: true, attributeFilter: ["data-theme", "style", "class"] });

  function weatherDescription(code) {
    const map = {
      0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
      45: "Туман", 48: "Туман", 51: "Слабая морось", 53: "Морось", 55: "Сильная морось",
      61: "Небольшой дождь", 63: "Дождь", 65: "Сильный дождь", 71: "Небольшой снег",
      73: "Снег", 75: "Сильный снег", 80: "Небольшой ливень", 81: "Ливень",
      82: "Сильный ливень", 95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза"
    };
    return map[Number(code)] || "Нет данных";
  }

  function renderWeather(data = null, message = "") {
    setScreenHeader("weather");
    const settings = loadMiniSettings();
    const weatherBlock = data ? `
      <section class="panel">
        <h2>${escapeHtml(data.location || settings.weatherCity || "Погода")}</h2>
        <p>${escapeHtml(weatherDescription(data.weatherCode))} · <b>${escapeHtml(String(data.temperature ?? "?"))}°C</b></p>
        <p class="muted">Ощущается ${escapeHtml(String(data.apparentTemperature ?? "?"))}°C · Влажность ${escapeHtml(String(data.humidity ?? "?"))}% · Ветер ${escapeHtml(String(data.windSpeed ?? "?"))} км/ч</p>
        ${data.updatedAt ? `<p class="muted">Обновлено: ${new Date(data.updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>` : ""}
      </section>` : `<section class="panel muted">${escapeHtml(message || "Укажи город и нажми «Обновить».")}</section>`;
    content.innerHTML = `<section class="panel">
      <h2>Настройка погоды</h2>
      <div class="mini-form">
        <input id="weatherCityInput" placeholder="Например: Кривой Рог" value="${escapeHtml(settings.weatherCity || "")}">
        <div class="mini-row">
          <button class="btn" onclick="refreshMiniWeather(true)">Обновить</button>
          <button class="btn secondary" onclick="renderMine()">Назад</button>
        </div>
      </div>
    </section>${weatherBlock}`;
    scrollToTop();
  }

  async function showWeather() {
    renderWeather();
    const settings = loadMiniSettings();
    if (settings.weatherCity) await refreshMiniWeather(false);
  }

  async function refreshMiniWeather(manual = true) {
    const input = document.getElementById("weatherCityInput");
    const city = (input ? input.value : loadMiniSettings().weatherCity || "").trim();
    if (!city) {
      renderWeather(null, "Укажи город для погоды.");
      return;
    }
    const settings = loadMiniSettings();
    settings.weatherCity = city;
    saveMiniSettings(settings);
    if (manual) renderWeather(null, "Обновляю погоду...");
    try {
      const data = await api(`/miniapp/weather?q=${encodeURIComponent(city)}`);
      renderWeather(data);
    } catch (error) {
      renderWeather(null, `Не удалось загрузить погоду: ${error.message || error}`);
    }
  }

  let radioResults = [];

  function loadLastRadioStation() {
    try {
      return JSON.parse(localStorage.getItem("miniAppLastRadioStation") || "null");
    } catch (_) {
      return null;
    }
  }

  function loadFavoriteRadioStations() {
    try {
      return JSON.parse(localStorage.getItem("miniAppFavoriteRadioStations") || "[]");
    } catch (_) {
      return [];
    }
  }

  function isFavoriteRadioStation(uuid) {
    return loadFavoriteRadioStations().some(station => station.uuid === uuid);
  }

  function renderRadioResults(emptyText = "Найди станцию или открой избранное.") {
    const target = document.getElementById("radioStations");
    if (!target) return;
    target.innerHTML = radioResults.map((station, index) => `
      <div class="radio-row">
        <button class="btn secondary" onclick="playRadioStation(${index})">
          ${escapeHtml(station.name || "Без названия")}
        </button>
        <button class="btn secondary favorite-btn" onclick="toggleFavoriteRadioStation(${index})">
          ${isFavoriteRadioStation(station.stationuuid) ? "★" : "☆"}
        </button>
      </div>
    `).join("") || `<div class="muted">${escapeHtml(emptyText)}</div>`;
  }

  function showRadio() {
    setScreenHeader("radio");
    const last = loadLastRadioStation();
    if (last && last.streamUrl && !radioPlayer.src) {
      radioPlayer.src = last.streamUrl;
    }
    if (radioPlayer.src) {
      radioPlayer.classList.add("active");
    }
    content.innerHTML = `<section class="panel">
      <h2>Radio Browser</h2>
      <div class="mini-form">
        <input id="radioSearch" placeholder="Название станции или жанр">
        <div class="mini-row">
          <button class="btn" onclick="searchRadioStations()">Найти</button>
          <button class="btn secondary" onclick="showFavoriteRadioStations()">Избранное</button>
        </div>
      </div>
      <div id="radioNow" class="muted" style="margin-top:10px">${last ? `Последняя станция: ${escapeHtml(last.name)}` : "Станция не выбрана."}</div>
      <p class="muted">Плеер закреплён снизу и не сбрасывается при переходе по Mini App.</p>
      <div id="radioStations" class="radio-list"></div>
      <button class="btn secondary" onclick="renderMine()">Назад в шахту</button>
    </section>`;
    renderRadioResults();
    scrollToTop();
  }

  async function searchRadioStations() {
    const query = document.getElementById("radioSearch").value.trim();
    const target = document.getElementById("radioStations");
    target.innerHTML = `<div class="muted">Ищу станции...</div>`;
    try {
      const result = await api(`/miniapp/radio/search?q=${encodeURIComponent(query)}`);
      radioResults = result.items || [];
      renderRadioResults("Станции не найдены.");
    } catch (error) {
      target.innerHTML = `<div class="muted">Не удалось загрузить станции: ${escapeHtml(error.message)}</div>`;
    }
  }

  function playRadioStation(index) {
    const station = radioResults[index];
    const url = station.streamUrl || station.url_resolved || station.url;
    radioPlayer.src = url;
    radioPlayer.classList.add("active");
    radioPlayer.play().catch(error => {
      const now = document.getElementById("radioNow");
      if (now) now.textContent = `Не удалось запустить: ${error.message || error}`;
    });
    document.getElementById("radioNow").textContent = `Сейчас играет: ${station.name || "Без названия"}`;
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: station.name || "Радио",
        artist: station.country || "Radio Browser",
      });
      navigator.mediaSession.playbackState = "playing";
    }
    localStorage.setItem("miniAppLastRadioStation", JSON.stringify({
      name: station.name || "Без названия",
      url: station.url_resolved || station.url || "",
      streamUrl: station.streamUrl || "",
      uuid: station.stationuuid || "",
    }));
    api("/miniapp/radio/click", {
      method: "POST", body: JSON.stringify({ item_key: station.stationuuid || station.uuid || "" })
    }).catch(() => {});
  }

  function toggleFavoriteRadioStation(index) {
    const station = radioResults[index];
    const uuid = station.stationuuid || station.uuid || "";
    const favorites = loadFavoriteRadioStations();
    const existing = favorites.findIndex(item => item.uuid === uuid);
    if (existing >= 0) favorites.splice(existing, 1);
    else favorites.push({
      name: station.name || "Без названия",
      url: station.url_resolved || station.url,
      streamUrl: station.streamUrl || "",
      uuid,
    });
    localStorage.setItem("miniAppFavoriteRadioStations", JSON.stringify(favorites));
    renderRadioResults();
  }

  function showFavoriteRadioStations() {
    radioResults = loadFavoriteRadioStations().map(station => ({
      name: station.name,
      url: station.url,
      url_resolved: station.url,
      streamUrl: station.streamUrl,
      stationuuid: station.uuid,
    }));
    renderRadioResults("В избранном пока нет станций.");
  }

  function profileInitials(name) {
    const parts = String(name || "Игрок").trim().split(/\s+/).filter(Boolean);
    return (parts.length > 1 ? parts[0][0] + parts[1][0] : parts[0].slice(0, 2)).toUpperCase();
  }

  function profileAvatarHtml(user, cosmetics = {}, small = false) {
    const frame = cosmetics.frame && cosmetics.frame.key ? cosmetics.frame.key : "";
    const frameClass =
      frame === "profile_frame_crystal" ? "frame-crystal" :
      frame === "profile_frame_copper" ? "frame-copper" :
      frame === "couple_frame" ? "frame-couple" : "";
    const fallback = `<span class="profile-avatar-fallback">${escapeHtml(profileInitials(user.fullName))}</span>`;
    const image = user.photoUrl
      ? `<img src="${escapeHtml(user.photoUrl)}" alt="" loading="${small ? "lazy" : "eager"}" onerror="this.parentElement.classList.remove('has-image');this.remove()">`
      : "";
    return `<div class="profile-avatar ${frameClass} ${image ? "has-image" : ""}">${image}${fallback}</div>`;
  }

  function profileHeroClass(cosmetics = {}) {
    const bg = cosmetics.background && cosmetics.background.key ? cosmetics.background.key : "";
    if (bg === "profile_bg_lava") return "bg-lava";
    if (bg === "profile_bg_old_mine") return "bg-old-mine";
    return "";
  }

  function profileBadgesHtml(profile) {
    const mine = profile.mine || {};
    const social = profile.social || {};
    const cosmetics = mine.cosmetics || {};
    const badges = [];
    if (social.relation !== "self" && social.relationTitle) badges.push(social.relationTitle);
    if (mine.rank) badges.push(mine.rank);
    (cosmetics.badges || []).slice(0, 2).forEach(item => badges.push(`${item.emoji || ""} ${item.title || ""}`.trim()));
    return badges.length
      ? `<div class="profile-badges">${badges.map(item => `<span class="profile-badge">${escapeHtml(item)}</span>`).join("")}</div>`
      : "";
  }

  function adminPanelButtonHtml(viewer) {
    return viewer && viewer.canViewAdminPanel
      ? `<button class="btn secondary" onclick="showAdminPanel()">🛡️ Админ</button>`
      : "";
  }

  function mineAdminButtonHtml(viewer) {
    return viewer && viewer.canViewMineAdmin
      ? `<button class="btn secondary" onclick="showMineAdmin()">⛏️ Шахта</button>`
      : "";
  }

  function roleRowHtml(item, group = {}, tab = {}) {
    const sourceTitle = item.source === "owner"
      ? "владелец"
      : item.source === "chat_admin"
        ? `админ чата${item.chatCount ? ` · чатов: ${Number(item.chatCount)}` : ""}`
      : item.source === "telegram_admin"
        ? (item.sourceTitle || "админ Telegram")
      : item.source === "delegated_admin"
        ? (item.sourceTitle || "права админки бота")
      : item.source === "moderation"
        ? (item.sourceTitle || `модерация${item.chatCount ? ` · чатов: ${Number(item.chatCount)}` : ""}`)
        : "Mini App";
    const removeButton = item.canRemove === false
      ? `<span class="muted">нельзя удалить</span>`
      : group.kind === "moderation" && tab.chatId
        ? `<button class="btn secondary" style="margin:0" onclick="clearModerationRoleFromRoles(${Number(tab.chatId)}, '${Number(item.user_id)}')">Удалить</button>`
        : `<button class="btn secondary" style="margin:0" onclick="clearProfileRole('${Number(item.user_id)}')">Удалить</button>`;
    return `<div class="role-row">
      <span>
        <b>${escapeHtml(item.username ? `@${item.username}` : (item.full_name || String(item.user_id)))}</b><br>
        <span class="muted">${escapeHtml(item.full_name || String(item.user_id))} · ID ${Number(item.user_id)} · ${escapeHtml(sourceTitle)}</span>
      </span>
      ${removeButton}
    </div>`;
  }

  function roleGroupHtml(group, tab = {}) {
    const items = (group.items || []).map(item => roleRowHtml(item, group, tab)).join("");
    const form = group.assignable === false ? "" : group.kind === "moderation" && tab.chatId ? `
      <div class="role-manager-form">
        <input id="roleTarget_${escapeHtml(group.key)}" placeholder="@ник или ID">
        <button class="btn" onclick="setModerationRoleFromRoles(${Number(tab.chatId)}, '${escapeHtml(group.key)}')">Добавить</button>
      </div>` : `
      <div class="role-manager-form">
        <input id="roleTarget_${escapeHtml(group.key)}" placeholder="@ник или ID">
        <button class="btn" onclick="setProfileRole('${escapeHtml(group.key)}', '${escapeHtml(group.label)}')">Добавить</button>
      </div>`;
    return `<details class="panel" open>
      <summary style="cursor:pointer;font-weight:900;font-size:20px">${escapeHtml(group.emoji || "")} ${escapeHtml(group.label)} · ${(group.items || []).length}</summary>
      ${group.limit ? `<p class="muted">${escapeHtml(group.limit)}</p>` : ""}
      <div class="role-list">${items || `<p class="muted">На этой роли пока никого нет.</p>`}</div>
      ${form}
    </details>`;
  }

  function roleTabsHtml(tabs, activeKey) {
    return `<div class="role-tabs">${(tabs || []).map(tab => {
      const active = tab.key === activeKey ? " active" : "";
      return `<button class="role-tab${active}" onclick="renderRoleManagerTab(${jsAttrString(tab.key)})">${escapeHtml(tab.title || tab.key)}</button>`;
    }).join("")}</div>`;
  }

  function renderRoleManagerTab(tabKey = null) {
    const tabs = window.currentRoleTabs || [];
    if (!tabs.length) {
      content.innerHTML = `<section class="panel muted">Роли не найдены.</section>`;
      return;
    }
    const active = tabs.find(tab => tab.key === tabKey) || tabs[0];
    window.currentRoleTabKey = active.key;
    content.innerHTML = `<section class="panel">
      <h2>Роли</h2>
      <p class="muted">Вкладки разделяют роли приложения и роли по конкретным группам: так видно, из какой группы пришёл админ или модер.</p>
      ${roleTabsHtml(tabs, active.key)}
      <p class="muted">${escapeHtml(active.subtitle || "")}</p>
    </section>
    ${(active.groups || []).map(group => roleGroupHtml(group, active)).join("")}
    <section class="panel"><button class="btn secondary" style="margin:0" onclick="showAdminPanel()">Назад в админ-панель</button></section>`;
    enableHorizontalWheelScroll(".role-tabs");
  }

  function adminSectionHtml(section) {
    const action = section.key === "roles" && section.enabled
      ? `<button class="btn secondary" onclick="showRoleManager()">Открыть роли</button>`
      : section.key === "mine" && section.enabled
        ? `<button class="btn secondary" onclick="showMineAdmin()">Открыть шахту</button>`
        : section.key === "moderation" && section.enabled
          ? `<button class="btn secondary" onclick="showModerationManager()">Открыть модерацию</button>`
          : section.key === "triggers" && section.enabled
            ? `<button class="btn secondary" onclick="showTriggerManager()">Открыть триггеры</button>`
            : `<span class="muted">Скоро</span>`;
    return `<div class="admin-list-row">
      <span>
        <b>${escapeHtml(section.title || section.key)}</b><br>
        <span class="muted">${escapeHtml(section.description || "")}</span>
      </span>
      ${action}
    </div>`;
  }

  async function showAdminPanel() {
    setScreenHeader("adminPanel");
    content.innerHTML = `<section class="panel muted">Загружаю админ-панель...</section>`;
    try {
      const data = await api("/miniapp/profile/admin");
      const summary = data.summary || {};
      const sections = data.sections || [];
      content.innerHTML = `<section class="panel">
        <h2>Админ-панель Mini App</h2>
        <p class="muted">Панель управления Mini App. Доступные разделы зависят от роли: владелец управляет ролями, модерация работает по правам в выбранном чате.</p>
        <div class="mine-admin-grid">
          <div class="mine-admin-card">Чаты<b>${Number(summary.chats || 0)}</b></div>
          <div class="mine-admin-card">Админы<b>${Number(summary.admins || 0)}</b></div>
          <div class="mine-admin-card">Модераторы<b>${Number(summary.moderators || 0)}</b></div>
          <div class="mine-admin-card">Игроки шахты<b>${Number(summary.minePlayers || 0)}</b></div>
        </div>
      </section>
      <section class="panel">
        <h2>Разделы</h2>
        <div class="role-list">${sections.map(adminSectionHtml).join("")}</div>
      </section>
      <section class="panel"><button class="btn secondary" style="margin:0" onclick="showProfile()">Назад к профилю</button></section>`;
      scrollToTop();
    } catch (error) {
      showError(error);
    }
  }

  async function showModerationManager(chatId = null) {
    setScreenHeader("adminPanel");
    content.innerHTML = `<section class="panel muted">Загружаю модерацию...</section>`;
    try {
      const path = chatId ? `/miniapp/profile/moderation?chat_id=${encodeURIComponent(chatId)}` : "/miniapp/profile/moderation";
      const data = await api(path);
      const chats = data.chats || [];
      const selectedChatId = Number(data.selectedChatId || 0);
      const selectedChat = data.selectedChat || {};
      const lock = data.lock || null;
      const lockText = lock
        ? `чат остановлен${lock.until_at ? ` до ${lock.until_at}` : " до ручного старта"}${lock.reason ? ` · ${lock.reason}` : ""}`
        : "чат открыт";
      const slowMode = data.slowMode || null;
      const slowModeText = slowMode && Number(slowMode.delay_seconds || 0) > 0
        ? `${Number(slowMode.delay_seconds)} сек`
        : "выключен";
      const lockLimit = data.chatLockLimitSeconds === null
        ? "без лимита"
        : Number(data.chatLockLimitSeconds || 0) > 0
          ? `до ${Math.floor(Number(data.chatLockLimitSeconds) / 60)} мин`
          : "нельзя";
      const chatTools = selectedChatId ? `<section class="panel">
        <h2>Режимы чата</h2>
        <p class="muted">Твоя роль: ${escapeHtml(data.viewerRoleTitle || "нет роли")}. Лимит чат-стопа: ${escapeHtml(lockLimit)}.</p>
        <div class="mine-admin-grid">
          <div class="mine-admin-card">Чат<b>${escapeHtml(lockText)}</b></div>
          <div class="mine-admin-card">Медленный режим<b>${escapeHtml(slowModeText)}</b></div>
        </div>
        ${data.canStopChat ? `<div class="mine-admin-form wide">
          <p class="muted wide">Закрывает чат для обычных участников. Пустой срок — до команды “Чат старт”.</p>
          <input id="modLockMinutes" placeholder="На сколько минут">
          <input id="modLockReason" placeholder="Причина, можно пусто">
          <button class="btn" onclick="setModerationChatLock(${selectedChatId})">Чат стоп</button>
          <button class="btn secondary" onclick="unlockModerationChat(${selectedChatId})">Чат старт</button>
        </div>` : `<p class="muted">Эта роль не может останавливать чат.</p>`}
        ${data.canSetSlowMode ? `<div class="mine-admin-form wide">
          <p class="muted wide">Бот удаляет слишком частые сообщения обычных участников. Модераторы и админы не ограничиваются.</p>
          <input id="modSlowDelay" value="${slowMode && Number(slowMode.delay_seconds || 0) > 0 ? Number(slowMode.delay_seconds) : ""}" placeholder="Пауза между сообщениями, сек">
          <button class="btn secondary" onclick="setModerationSlowMode(${selectedChatId})">Применить</button>
          <button class="btn secondary" onclick="clearModerationSlowMode(${selectedChatId})">Выключить</button>
        </div>` : `<p class="muted">Медленный режим доступен модератору, старшему, админу и владельцу.</p>`}
      </section>` : "";
      content.innerHTML = `<section class="panel">
        <h2>Модерация</h2>
        <p class="muted">Здесь только настройки модерации выбранной группы. Роли назначаются в отдельном разделе “Роли”, логи уходят в staff-группу.</p>
        <div class="mine-admin-form">
          <select id="moderationChatSelect" class="wide" onchange="showModerationManager(this.value)">
            ${triggerChatOptionsHtml(chats, selectedChatId)}
          </select>
        </div>
      </section>
      ${chatTools}
      ${selectedChatId ? "" : `<section class="panel muted">Нет доступных чатов для модерации.</section>`}
      <section class="panel"><button class="btn secondary" style="margin:0" onclick="showAdminPanel()">Назад в админ-панель</button></section>`;
      scrollToTop();
    } catch (error) {
      showError(error);
    }
  }

  async function setModerationRoleFromRoles(chatId, role) {
    const target = document.getElementById(`roleTarget_${role}`)?.value || "";
    if (!target.trim()) {
      alert("Укажи пользователя.");
      return;
    }
    try {
      await api("/miniapp/profile/moderation/roles", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), target, role })
      });
      showNotice("Роль модерации выдана.");
      showRoleManager(window.currentRoleTabKey);
    } catch (error) {
      alert(error.message);
    }
  }

  async function clearModerationRoleFromRoles(chatId, target) {
    if (!confirm("Снять роль модерации в этой группе?")) return;
    try {
      await api("/miniapp/profile/moderation/roles/clear", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), target: String(target) })
      });
      showNotice("Роль модерации снята.");
      showRoleManager(window.currentRoleTabKey);
    } catch (error) {
      alert(error.message);
    }
  }

  async function setModerationChatLock(chatId) {
    const minutesRaw = (document.getElementById("modLockMinutes")?.value || "").trim();
    const reason = document.getElementById("modLockReason")?.value || "";
    const seconds = minutesRaw ? Math.max(1, Math.round(Number(minutesRaw) * 60)) : null;
    if (minutesRaw && !Number.isFinite(seconds)) {
      alert("Минуты должны быть числом.");
      return;
    }
    try {
      await api("/miniapp/profile/moderation/chat-lock", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), seconds, reason })
      });
      showNotice("Чат остановлен.");
      showModerationManager(chatId);
    } catch (error) {
      alert(error.message);
    }
  }

  async function unlockModerationChat(chatId) {
    try {
      await api("/miniapp/profile/moderation/chat-unlock", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), seconds: 1, reason: "" })
      });
      showNotice("Чат открыт.");
      showModerationManager(chatId);
    } catch (error) {
      alert(error.message);
    }
  }

  async function setModerationSlowMode(chatId) {
    const rawDelay = (document.getElementById("modSlowDelay")?.value ?? "").trim();
    const normalizedDelay = rawDelay.toLowerCase();
    const delay = rawDelay === "" || ["0", "выкл", "выключить", "off"].includes(normalizedDelay)
      ? 0
      : Math.max(0, Math.round(Number(rawDelay)));
    if (!Number.isFinite(delay)) {
      alert("Пауза должна быть числом секунд.");
      return;
    }
    try {
      await api("/miniapp/profile/moderation/slow-mode", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), delay })
      });
      showNotice(delay ? `Медленный режим: ${delay} сек.` : "Медленный режим выключен.");
      showModerationManager(chatId);
    } catch (error) {
      alert(error.message);
    }
  }

  async function clearModerationSlowMode(chatId) {
    try {
      await api("/miniapp/profile/moderation/slow-mode", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), delay: 0 })
      });
      showNotice("Медленный режим выключен.");
      showModerationManager(chatId);
    } catch (error) {
      alert(error.message);
    }
  }

  function triggerChatOptionsHtml(chats, selectedChatId) {
    return (chats || []).map(chat => {
      const selected = Number(chat.id) === Number(selectedChatId) ? " selected" : "";
      const title = chat.username ? `${chat.title} (@${chat.username})` : chat.title;
      return `<option value="${Number(chat.id)}"${selected}>${escapeHtml(title)}</option>`;
    }).join("");
  }

  function triggerRowHtml(item) {
    const variants = item.variants || [];
    const mediaCount = variants.filter(variant => variant.hasMedia).length;
    const brokenCount = variants.filter(variant => variant.mediaBroken).length;
    const textCount = variants.filter(variant => !variant.hasMedia && (variant.text || "").trim()).length;
    const aliasText = Number(item.aliasCount || 0) > 0 ? ` · +${Number(item.aliasCount || 0)} форм` : "";
    const brokenText = brokenCount ? ` · ⚠️ битых медиа: ${brokenCount}` : "";
    const summary = [
      textCount ? `${textCount} текст.` : "",
      mediaCount ? `${mediaCount} медиа` : ""
    ].filter(Boolean).join(" · ") || (item.hasMedia ? "медиа" : "1 ответ");
    return `<div class="admin-list-row">
      <span>
        <b>${escapeHtml(item.trigger)}</b><br>
        <span class="muted">${escapeHtml(summary)}${aliasText}${escapeHtml(brokenText)} · ${escapeHtml(item.text || "Без текста")}</span>
      </span>
      <span class="utility-actions" style="margin:0">
        <button class="btn secondary" style="margin:0" onclick="editMiniAppTrigger(${Number(item.chatId)}, ${jsAttrString(item.trigger)})">Редактировать</button>
        <button class="btn danger" style="margin:0" onclick="deleteMiniAppTrigger(${Number(item.chatId)}, ${jsAttrString(item.trigger)})">Удалить</button>
      </span>
    </div>`;
  }

  function triggerVariantRows(editor) {
    const variants = editor && Array.isArray(editor.variants) && editor.variants.length
      ? editor.variants
      : (editor && editor.text ? [{ variantType: "text", text: editor.text }] : [{ variantType: "text", text: "" }]);
    const textVariants = variants.filter(item => (item.variantType || "text") === "text").slice(0, 10);
    return (textVariants.length ? textVariants : [{ text: "" }]).map((item, index) => `<div class="trigger-answer-row">
      <textarea class="triggerAnswerInput" placeholder="Вариант ответа ${index + 1}">${escapeHtml(item.text || "")}</textarea>
      <button class="btn danger" style="margin:0" onclick="this.closest('.trigger-answer-row').remove()">×</button>
    </div>`).join("");
  }

  function triggerMediaVariant(editor, variantType) {
    const variants = editor && Array.isArray(editor.variants) ? editor.variants : [];
    return variants.find(item => (item.variantType || "") === variantType) || {};
  }

  function triggerMediaBoxHtml(editor, variantType, title, accept, note) {
    const item = triggerMediaVariant(editor, variantType);
    const mediaFileId = item.mediaBroken ? "" : (item.mediaFileId || "");
    const status = item.mediaBroken
      ? "Старый локальный файл недоступен. Загрузите медиа заново."
      : mediaFileId
        ? "Сейчас сохранено медиа. Новый файл заменит старый."
        : note;
    return `<div class="trigger-media-box" data-trigger-media="${escapeHtml(variantType)}" data-media-file-id="${escapeHtml(mediaFileId)}" data-media-type="${escapeHtml(item.mediaType || variantType)}">
      <b>${escapeHtml(title)}</b>
      <input class="triggerMediaFile" type="file" accept="${escapeHtml(accept)}">
      <textarea class="triggerMediaCaption" placeholder="Подпись, необязательно">${escapeHtml(item.text || "")}</textarea>
      <span class="trigger-media-status">${escapeHtml(status)}</span>
    </div>`;
  }

  function triggerEditorHtml(chatId, editor) {
    if (!editor) return "";
    return `<section class="panel">
      <h2>${editor.trigger ? "Редактировать триггер" : "Добавить триггер"}</h2>
      <div class="mine-admin-form">
        <input id="triggerWord" class="wide" placeholder="Слово или фраза" value="${escapeHtml(editor.trigger || "")}">
        <textarea id="triggerAliases" class="wide" placeholder="Формы и синонимы через запятую: спать, спал, сплю">${escapeHtml((editor.aliases || []).join(", "))}</textarea>
        <div class="wide">
          <p class="muted">Добавить ответ. Максимум 10 текстовых вариантов, бот выберет случайный.</p>
          <div id="triggerAnswers" class="trigger-answer-list">${triggerVariantRows(editor)}</div>
          <button class="btn secondary" style="margin-top:8px" onclick="addTriggerAnswerInput()">Добавить ответ</button>
        </div>
        <div class="wide">${triggerMediaBoxHtml(editor, "photo", "Фото или фото с подписью", "image/*", "Можно добавить фото и подпись.")}</div>
        <div class="wide">${triggerMediaBoxHtml(editor, "animation", "GIF или GIF с подписью", "image/gif,video/mp4", "Можно добавить GIF/анимацию и подпись.")}</div>
        <div class="wide">${triggerMediaBoxHtml(editor, "audio", "Аудио-метка до 30 сек", "audio/*", "Загрузи короткую аудио-метку до 30 секунд.")}</div>
        <div class="wide">${triggerMediaBoxHtml(editor, "video", "Короткое видео до 15 сек", "video/*", "Можно добавить короткое видео и подпись.")}</div>
        <button class="btn" onclick="saveMiniAppTrigger(${Number(chatId)})">Сохранить</button>
        <button class="btn secondary" onclick="showTriggerManager(${Number(chatId)})">Отмена</button>
      </div>
    </section>`;
  }

  function addTriggerAnswerInput() {
    const list = document.getElementById("triggerAnswers");
    if (!list) return;
    if (list.querySelectorAll(".triggerAnswerInput").length >= 10) {
      alert("Максимум 10 текстовых ответов на один триггер.");
      return;
    }
    const row = document.createElement("div");
    row.className = "trigger-answer-row";
    row.innerHTML = `<textarea class="triggerAnswerInput" placeholder="Вариант ответа"></textarea><button class="btn danger" style="margin:0" onclick="this.closest('.trigger-answer-row').remove()">×</button>`;
    list.appendChild(row);
  }

  function editMiniAppTrigger(chatId, trigger) {
    const item = (window.currentMiniAppTriggers || []).find(row => row.trigger === trigger);
    showTriggerManager(chatId, item || { trigger, text: "" });
  }

  async function showTriggerManager(chatId = null, editor = null) {
    setScreenHeader("adminPanel");
    content.innerHTML = `<section class="panel muted">Загружаю триггеры...</section>`;
    try {
      const path = chatId ? `/miniapp/profile/triggers?chat_id=${encodeURIComponent(chatId)}` : "/miniapp/profile/triggers";
      const data = await api(path);
      const chats = data.chats || [];
      const selectedChatId = Number(data.selectedChatId || 0);
      const triggers = data.triggers || [];
      window.currentMiniAppTriggers = triggers;
      const selectedChat = data.selectedChat || {};
      const addButton = selectedChatId
        ? `<button class="btn" style="margin:0" onclick="showTriggerManager(${selectedChatId}, { trigger: '', variants: [{ variantType: 'text', text: '' }] })">Добавить триггер</button>`
        : "";
      content.innerHTML = `<section class="panel">
        <h2>Триггеры</h2>
        <p class="muted">Выбери чат, добавь слово/фразу и ответ. Если у старого триггера было медиа, при редактировании текста оно сохранится.</p>
        <div class="mine-admin-form">
          <select id="triggerChatSelect" class="wide" onchange="showTriggerManager(this.value)">
            ${triggerChatOptionsHtml(chats, selectedChatId)}
          </select>
          ${addButton}
        </div>
      </section>
      ${selectedChatId ? triggerEditorHtml(selectedChatId, editor) : ""}
      <section class="panel">
        <h2>${escapeHtml(selectedChat.title || "Триггеры")}</h2>
        <div class="role-list">${triggers.map(triggerRowHtml).join("") || `<p class="muted">В этом чате пока нет триггеров.</p>`}</div>
      </section>
      <section class="panel"><button class="btn secondary" style="margin:0" onclick="showAdminPanel()">Назад в админ-панель</button></section>`;
      scrollToTop();
    } catch (error) {
      showError(error);
    }
  }

  async function saveMiniAppTrigger(chatId) {
    const trigger = document.getElementById("triggerWord")?.value || "";
    const aliases = (document.getElementById("triggerAliases")?.value || "")
      .split(/[,\n;]/)
      .map(item => item.trim())
      .filter(Boolean)
      .slice(0, 30);
    if (!trigger.trim()) {
      alert("Укажи триггер.");
      return;
    }
    try {
      const variants = [];
      document.querySelectorAll(".triggerAnswerInput").forEach(node => {
        const text = node.value || "";
        if (text.trim()) variants.push({ variantType: "text", text });
      });
      for (const box of document.querySelectorAll("[data-trigger-media]")) {
        const variantType = box.dataset.triggerMedia || "";
        const input = box.querySelector(".triggerMediaFile");
        const caption = box.querySelector(".triggerMediaCaption")?.value || "";
        let mediaFileId = box.dataset.mediaFileId || "";
        let mediaType = box.dataset.mediaType || variantType;
        if (input && input.files && input.files[0]) {
          const form = new FormData();
          form.append("file", input.files[0]);
          const uploaded = await apiForm(`/miniapp/profile/triggers/media?media_type=${encodeURIComponent(variantType)}`, form);
          mediaFileId = uploaded.mediaFileId || "";
          mediaType = uploaded.mediaType || variantType;
          box.dataset.mediaFileId = mediaFileId;
          box.dataset.mediaType = mediaType;
          const status = box.querySelector(".trigger-media-status");
          if (status) {
            status.textContent = uploaded.storage === "telegram"
              ? "Медиа сохранено в Telegram, сохраняю триггер..."
              : "Медиа сохранено локально, сохраняю триггер...";
          }
        }
        if (mediaFileId) {
          variants.push({ variantType, text: caption, mediaType, mediaFileId });
        }
      }
      if (!variants.length) {
        alert("Добавь хотя бы один ответ или медиа.");
        return;
      }
      await api("/miniapp/profile/triggers", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), trigger, aliases, variants })
      });
      showNotice("Триггер сохранён.");
      showTriggerManager(chatId);
    } catch (error) {
      alert(error.message);
    }
  }

  async function deleteMiniAppTrigger(chatId, trigger) {
    if (!confirm(`Удалить триггер «${trigger}»?`)) return;
    try {
      await api("/miniapp/profile/triggers/delete", {
        method: "POST",
        body: JSON.stringify({ chatId: Number(chatId), trigger })
      });
      showNotice("Триггер удалён.");
      showTriggerManager(chatId);
    } catch (error) {
      alert(error.message);
    }
  }

  async function showRoleManager(tabKey = null) {
    setScreenHeader("adminPanel");
    content.innerHTML = `<section class="panel muted">Загружаю роли...</section>`;
    try {
      const data = await api("/miniapp/profile/roles");
      window.currentRoleTabs = data.tabs || [{ key: "legacy", title: "Роли приложения", groups: data.groups || [] }];
      renderRoleManagerTab(tabKey || window.currentRoleTabKey || "app");
    } catch (error) {
      showError(error);
    }
  }

  async function setProfileRole(roleKey = "", label = "") {
    const target = document.getElementById(`roleTarget_${roleKey}`)?.value || "";
    if (!target.trim() || !label.trim()) {
      alert("Укажи пользователя.");
      return;
    }
    try {
      const result = await api("/miniapp/profile/roles", {
        method: "POST",
        body: JSON.stringify({ target, label })
      });
      showNotice(`Роль выдана: ${result.target ? result.target.fullName : target}`);
      showRoleManager(window.currentRoleTabKey);
    } catch (error) {
      alert(error.message);
    }
  }

  async function clearProfileRole(target) {
    if (!confirm("Удалить роль у пользователя?")) return;
    try {
      await api("/miniapp/profile/roles/clear", {
        method: "POST",
        body: JSON.stringify({ target: String(target) })
      });
      showNotice("Роль удалена.");
      showRoleManager(window.currentRoleTabKey);
    } catch (error) {
      alert(error.message);
    }
  }

  function mineAdminPlayerTitleHtml(player, prefix = "") {
    const name = player.full_name || String(player.user_id);
    const username = player.username
      ? `<span class="mine-admin-username"><span class="mine-admin-username-label">Ник:</span>@${escapeHtml(player.username)}</span>`
      : "";
    return `<div class="mine-admin-title"><b>${escapeHtml(prefix + name)}</b>${username}</div>`;
  }

  function mineAdminRowHtml(player, canManage = false) {
    const action = canManage
      ? `<span class="utility-actions" style="margin:0"><button class="btn secondary" style="margin:0" onclick="prefillMineGrant(${Number(player.user_id)})">Выбрать</button><button class="btn danger" style="margin:0" onclick="deleteMinePlayer(${Number(player.user_id)})">Удалить</button><button class="btn danger" style="margin:0" onclick="blockMinePlayer(${Number(player.user_id)}, true)">Бан+удалить</button></span>`
      : `<span class="muted">просмотр</span>`;
    return `<div class="mine-admin-row">
      <span>
        ${mineAdminPlayerTitleHtml(player)}<br>
        <span class="muted">ID ${Number(player.user_id)} · ${Number(player.total_depth || 0)} м · ${Number(player.coins || 0)} котоинов · удача ${Number(player.luck || 0)}/100</span>
      </span>
      ${action}
    </div>`;
  }

  function mineAdminBlockRowHtml(item, canManage = false) {
    const action = canManage
      ? `<button class="btn secondary" style="margin:0" onclick="unblockMinePlayer(${Number(item.user_id)})">Разблокировать</button>`
      : `<span class="muted">бан</span>`;
    return `<div class="mine-admin-row">
      <span>
        ${mineAdminPlayerTitleHtml(item)}<br>
        <span class="muted">ID ${Number(item.user_id)}${item.reason ? ` · ${escapeHtml(item.reason)}` : ""}</span>
      </span>
      ${action}
    </div>`;
  }

  function mineAdminTopHtml(title, rows, valueKey, suffix = "") {
    const items = (rows || []).map((player, index) => `<div class="mine-admin-row">
      <span>
        ${mineAdminPlayerTitleHtml(player, `${index + 1}. `)}<br>
        <span class="muted">ID ${Number(player.user_id)} · ${Number(player[valueKey] || 0)}${suffix}</span>
      </span>
    </div>`).join("");
    return `<section class="panel">
      <h2>${escapeHtml(title)}</h2>
      <div class="role-list">${items || `<p class="muted">Пока пусто.</p>`}</div>
    </section>`;
  }

  function prefillMineGrant(userId) {
    const input = document.getElementById("mineGrantUserId");
    if (input) {
      input.value = String(userId);
      input.focus();
    }
  }

  async function showMineAdmin(page = 1) {
    setScreenHeader("mineAdmin");
    content.innerHTML = `<section class="panel muted">Загружаю панель шахты...</section>`;
    try {
      const data = await api("/miniapp/profile/mine-admin?per_page=0");
      const summary = data.summary || {};
      const blocked = data.blocked || [];
      const canManage = Boolean(data.canManage);
      const grantForm = canManage ? `<section class="panel">
        <h2>Управление игроком</h2>
        <p class="muted">Как в Abstergo: укажи ID игрока, заполни только нужные поля. Отрицательные значения снимают ресурс.</p>
        <div class="mine-admin-form">
          <input id="mineGrantUserId" class="wide" placeholder="User ID">
          <input id="mineGrantCoins" type="number" placeholder="Котоины +/-">
          <input id="mineGrantLuck" type="number" min="0" max="100" placeholder="Удача 0-100">
          <input id="mineGrantExtra" type="number" placeholder="Раскопки +/-">
          <input id="mineGrantTickets" type="number" placeholder="Билеты +/-">
          <input id="mineGrantSuper" type="number" placeholder="Супер-игры +/-">
          <label class="muted wide"><input id="mineGrantCooldown" type="checkbox"> сбросить ожидание копки</label>
          <button class="btn wide" onclick="submitMineGrant()">Сохранить</button>
        </div>
      </section>
      <section class="panel">
        <h2>Опасная зона</h2>
        <p class="muted">Удаление стирает прогресс шахты. Блокировка запрещает Mini App шахты и команду копай.</p>
        <div class="mine-admin-form">
          <input id="mineDangerUserId" class="wide" placeholder="User ID">
          <input id="mineDangerReason" class="wide" placeholder="Причина блокировки, необязательно">
          <button class="btn danger" onclick="deleteMinePlayer()">Удалить из шахты</button>
          <button class="btn danger" onclick="blockMinePlayer(null, false)">Заблокировать</button>
          <button class="btn danger wide" onclick="blockMinePlayer(null, true)">Заблокировать и удалить прогресс</button>
        </div>
      </section>` : `<section class="panel muted">Режим просмотра: управление доступно только владельцу.</section>`;
      content.innerHTML = `<div class="mine-admin-screen">
      <section class="panel">
        <h2>Сводка</h2>
        <div class="mine-admin-grid">
          <div class="mine-admin-card">Игроки<b>${Number(summary.players || 0)}</b></div>
          <div class="mine-admin-card">Глубина<b>${Number(summary.totalDepth || 0)} м</b></div>
        </div>
      </section>
      ${grantForm}
      ${mineAdminTopHtml("Топ глубины", data.top && data.top.depth, "total_depth", " м")}
      ${mineAdminTopHtml("Топ котоинов", data.top && data.top.coins, "coins", " кот.")}
      <section class="panel">
        <h2>Заблокированы в копай</h2>
        <div class="role-list">${blocked.map(item => mineAdminBlockRowHtml(item, canManage)).join("") || `<p class="muted">Блокировок пока нет.</p>`}</div>
      </section>
      <section class="panel"><button class="btn secondary" style="margin:0" onclick="showProfile()">Назад к профилю</button></section>
      </div>`;
      scrollToTop();
    } catch (error) {
      showError(error);
    }
  }

  async function submitMineGrant() {
    const numberOrNull = id => {
      const value = document.getElementById(id)?.value;
      return value === "" || value === undefined ? null : Number(value);
    };
    const userId = numberOrNull("mineGrantUserId");
    if (!userId) {
      alert("Укажи User ID игрока.");
      return;
    }
    const payload = {
      userId,
      coins: numberOrNull("mineGrantCoins"),
      luck: numberOrNull("mineGrantLuck"),
      extraDigs: numberOrNull("mineGrantExtra"),
      goldenTickets: numberOrNull("mineGrantTickets"),
      superPasses: numberOrNull("mineGrantSuper"),
      clearCooldown: Boolean(document.getElementById("mineGrantCooldown")?.checked)
    };
    try {
      const result = await api("/miniapp/profile/mine-admin/grant", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      showNotice(result.message || "Шахта обновлена.");
      showMineAdmin();
    } catch (error) {
      alert(error.message);
    }
  }

  function mineDangerUserId(userId = null) {
    const raw = userId || document.getElementById("mineDangerUserId")?.value || document.getElementById("mineGrantUserId")?.value || "";
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }

  async function deleteMinePlayer(userId = null) {
    const target = mineDangerUserId(userId);
    if (!target) return alert("Укажи User ID игрока.");
    if (!confirm("Удалить игрока из шахты? Прогресс будет стёрт.")) return;
    try {
      const result = await api("/miniapp/profile/mine-admin/delete", {
        method: "POST",
        body: JSON.stringify({ userId: target })
      });
      showNotice(result.message || "Игрок удалён.");
      showMineAdmin();
    } catch (error) {
      alert(error.message);
    }
  }

  async function blockMinePlayer(userId = null, deletePlayer = false) {
    const target = mineDangerUserId(userId);
    if (!target) return alert("Укажи User ID игрока.");
    const reason = document.getElementById("mineDangerReason")?.value || "";
    if (!confirm(deletePlayer ? "Заблокировать и удалить прогресс игрока?" : "Заблокировать игроку шахту и команду копай?")) return;
    try {
      const result = await api("/miniapp/profile/mine-admin/block", {
        method: "POST",
        body: JSON.stringify({ userId: target, reason, deletePlayer })
      });
      showNotice(result.message || "Игрок заблокирован.");
      showMineAdmin();
    } catch (error) {
      alert(error.message);
    }
  }

  async function unblockMinePlayer(userId) {
    if (!confirm("Снять блокировку шахты?")) return;
    try {
      const result = await api("/miniapp/profile/mine-admin/unblock", {
        method: "POST",
        body: JSON.stringify({ userId: Number(userId) })
      });
      showNotice(result.message || "Блокировка снята.");
      showMineAdmin();
    } catch (error) {
      alert(error.message);
    }
  }

  function friendRowHtml(friend) {
    const user = { fullName: friend.fullName, username: friend.username, photoUrl: friend.photoUrl };
    return `<button class="friend-row" onclick="showProfile(${Number(friend.id)})">
      ${profileAvatarHtml(user, {}, true)}
      <span>
        <span class="friend-name">${escapeHtml(friend.fullName || "Игрок")}</span>
        <span class="friend-meta">${friend.username ? `@${escapeHtml(friend.username)} · ` : ""}${escapeHtml(friend.relationTitle || "Друг")}</span>
      </span>
      <span class="friend-open">›</span>
    </button>`;
  }

  function renderProfile(profile) {
    currentProfile = profile;
    setScreenHeader("profile");
    const user = profile.user || {};
    const premium = profile.premium || {};
    const plan = premium.plan || {};
    const mine = profile.mine || {};
    const cosmetics = mine.cosmetics || {};
    const social = profile.social || {};
    const viewer = profile.viewer || {};
    const friends = social.friends || [];
    const isSelf = viewer.isSelf !== false;
    const premiumText = premium.active ? (plan.title || "Premium активен") : "не активен";
    const rareAchievements = (mine.rareAchievements || []).slice(0, 5).map(item => `
      <div class="achievement-card ${escapeHtml(item.rarity || "common")}">
        <b>${escapeHtml(item.name)}</b>
        <div class="achievement-rarity">${escapeHtml(item.rarityTitle || "Обычное")}</div>
      </div>
    `).join("");
    const cosmeticsBadges = (cosmetics.badges || []).map(item => `${escapeHtml(item.emoji || "")} ${escapeHtml(item.title || "")}`).join(" · ");
    const cosmeticsHtml = (cosmetics.frame || cosmetics.background || cosmeticsBadges) ? `
      <section class="panel">
        <h2>Оформление</h2>
        <p class="muted">Рамка: <b>${escapeHtml((cosmetics.frame && cosmetics.frame.title) || "не выбрана")}</b></p>
        <p class="muted">Фон: <b>${escapeHtml((cosmetics.background && cosmetics.background.title) || "не выбран")}</b></p>
        ${cosmeticsBadges ? `<p class="muted">Значки: <b>${cosmeticsBadges}</b></p>` : ""}
      </section>` : "";
    const friendsPreview = friends.slice(0, 3).map(friendRowHtml).join("");
    content.innerHTML = `<section class="panel profile-hero ${profileHeroClass(cosmetics)}">
      ${profileAvatarHtml(user, cosmetics)}
      <div class="profile-title">
        <h2>${escapeHtml(user.fullName || "Профиль")}</h2>
        <div class="profile-username">${user.username ? `@${escapeHtml(user.username)}` : "username не указан"}</div>
        ${profileBadgesHtml(profile)}
      </div>
    </section>
    <section class="panel">
      <div class="profile-grid">
        <div class="profile-card">Premium<b>${escapeHtml(premiumText)}</b></div>
        <div class="profile-card">Ранг<b>${escapeHtml(mine.rank || "Новичок")}</b></div>
        <div class="profile-card">Котоины<b>${mine.coins || 0}</b></div>
        <div class="profile-card">Глубина<b>${mine.totalDepth || 0} м</b></div>
        <div class="profile-card">Уровень<b>${mine.level || 0}</b></div>
        <div class="profile-card">Удача<b>${mine.luck || 0}/100</b></div>
      </div>
      <div class="profile-actions">
        <button class="btn secondary" onclick="showFriendsInfo()">${friends.length ? `Друзья: ${friends.length}` : "Друзья"}</button>
        ${isSelf ? `<button class="btn secondary" onclick="showBag()">Сумка</button>` : `<button class="btn secondary" onclick="showProfile()">Мой профиль</button>`}
        ${adminPanelButtonHtml(viewer)}
        ${mineAdminButtonHtml(viewer)}
      </div>
      ${isSelf ? themeSwitcherHtml() : ""}
    </section>
    ${friendsPreview ? `<section class="panel"><h2>${isSelf ? "Друзья" : "Связи"}</h2><div class="friend-list">${friendsPreview}</div>${friends.length > 3 ? `<button class="btn secondary" onclick="showFriendsInfo()">Показать всех: ${friends.length}</button>` : ""}</section>` : ""}
    <section class="panel">
      <h2>Шахта</h2>
      <p class="muted">Рекорд: <b>${mine.bestSessionDepth || 0} м</b> · Серия: <b>${mine.streak || 0}</b> · Маршрут: <b>${escapeHtml(mine.route || "не выбран")}</b></p>
      <p class="muted">Достижения: <b>${mine.achievementsTotal || 0}/${mine.achievementsKnown || 0}</b></p>
    </section>
    ${cosmeticsHtml}
    ${rareAchievements ? `<section class="panel"><h2>Редчайшие достижения</h2><div class="achievement-showcase">${rareAchievements}</div></section>` : ""}
    <section class="panel"><button class="btn secondary" style="margin:0" onclick="${isSelf ? "renderMine()" : "showProfile()"}">${isSelf ? "Назад в шахту" : "Назад к моему профилю"}</button></section>`;
    scrollToTop();
  }

  function showFriendsInfo() {
    setScreenHeader("profile");
    const profile = currentProfile || {};
    const social = profile.social || {};
    const friends = social.friends || [];
    const viewer = profile.viewer || {};
    const isSelf = viewer.isSelf !== false;
    content.innerHTML = `<section class="panel">
      <h2>${isSelf ? "Друзья" : "Связи профиля"}</h2>
      <p class="muted">${friends.length ? "Нажми на человека, чтобы открыть его профиль." : "Пока нет друзей из общих чатов."}</p>
      ${friends.length ? `<div class="friend-list">${friends.map(friendRowHtml).join("")}</div>` : ""}
      <button class="btn secondary" onclick="${isSelf ? "showProfile()" : "showProfile()"}">Назад к профилю</button>
    </section>`;
    scrollToTop();
  }

  async function showProfile(userId = null) {
    if (activeView !== "profile") {
      profileReturnView = activeView || "mine";
    }
    setScreenHeader("profile");
    content.innerHTML = `<section class="panel muted">Загружаю профиль...</section>`;
    try {
      const path = userId ? `/miniapp/profile?user_id=${encodeURIComponent(userId)}` : "/miniapp/profile";
      renderProfile(await api(path));
    } catch (error) {
      showError(error);
    }
  }

  function shiftContractHtml() {
    const shift = state && state.rankShift ? state.rankShift : null;
    if (!shift) return "";
    if (!shift.available) {
      return `<section class="panel shift-card">
        <h2>Сменное задание</h2>
        <p class="muted">${escapeHtml(shift.reason || "Открывается после покупки ранга.")}</p>
      </section>`;
    }
    if (shift.selected) {
      const selected = shift.selected;
      const status = selected.claimed ? "выполнено" : `${selected.progress}/${selected.target}`;
      return `<section class="panel shift-card">
        <div class="section-title"><h2>Сменное задание</h2><span class="counter">${escapeHtml(shift.rank || "")}</span></div>
        <p><b>${escapeHtml(selected.name)}</b></p>
        <p class="muted">Прогресс: <b>${escapeHtml(status)}</b> · награда: <b>${escapeHtml(selected.reward)}</b>.</p>
      </section>`;
    }
    const options = (shift.options || []).map(item => `
      <button class="btn secondary" onclick="selectShiftContract('${item.key}')">
        ${escapeHtml(item.name)} · ${escapeHtml(item.reward)}
      </button>`).join("");
    return `<section class="panel shift-card">
      <div class="section-title"><h2>Сменное задание</h2><span class="counter">${escapeHtml(shift.rank || "")}</span></div>
      <p class="muted">Выбери одну цель на сегодня.</p>
      <div class="shift-options">${options}</div>
    </section>`;
  }

  function mineHtml() {
    if (!state.registered) {
      return `<section class="panel">
        <h2>Новая шахта</h2>
        <p>Зарегистрируйся, чтобы начать раскопки. Прогресс общий для всех групп и Mini App.</p>
        <button class="btn" onclick="registerMine()">Начать игру</button>
      </section>`;
    }
    const disabled = isCoolingDown();
    const cooldown = disabled
      ? `Следующая раскопка будет доступна: ${new Date(state.cooldownUntil).toLocaleString()}`
      : "Раскопка доступна сейчас.";
    return `
      <div class="stats">
        <div class="stat">🪙<b id="mineCoins">${state.coins}</b></div>
        <div class="stat">🍀<b>${state.luck}/100</b></div>
        <div class="stat">🏆<b>${state.record} м</b></div>
      </div>
      ${utilityActionsHtml()}
      ${shiftContractHtml()}
      ${interactiveMineHtml(disabled, cooldown)}
      ${goldTicketHtml()}
      ${superGameHtml()}
      <section class="panel">Уровень <b>${state.level}</b> · XP <b>${state.xp}</b> · серия <b>${state.streak}</b></section>
      <section class="panel">
        <button class="btn secondary" style="margin:0" onclick="showBag()">Сумка</button>
      </section>`;
  }

  function interactiveMineHtml(disabled, cooldown) {
    const dig = state.interactiveMine;
    if (!dig) {
      const buttonDisabled = disabled;
      const buttonText = buttonDisabled ? "⏳ Ручная вылазка недоступна" : "⛏️ Начать ручную вылазку";
      return `<section class="panel">
        <div class="muted">Ручная вылазка</div>
        <div class="depth">0/10 м</div>
        <div class="meter"><div class="fill" style="width:0%"></div></div>
        <button class="btn" ${buttonDisabled ? "disabled" : ""} onclick="startInteractiveDig(this)">${buttonText}</button>
        <div class="muted" style="margin-top:10px">Условия: клетки, события, ресурсы и выборы по ходу вылазки. Торговец ждёт снаружи в сумке.</div>
        <div class="muted" style="margin-top:8px">${escapeHtml(cooldown)}</div>
      </section>`;
    }
    const stage = dig.stage || {};
    const progress = Math.max(0, Math.min(10, Number(dig.depth || 0)));
    const header = `<div class="section-title"><h2>${escapeHtml(dig.mineEmoji || "⛏")} ${escapeHtml(dig.mineTitle || "Шахта")}</h2><span class="counter">${progress}/10 м</span></div>
      <div class="meter"><div class="fill" style="width:${progress * 10}%"></div></div>
      <p class="muted">Прочность: <b>${dig.durability}/${dig.maxDurability}</b> · Временная добыча: <b>${dig.temporaryCoins}</b> 🪙 · Ресурсы: <b>${dig.oreUnits || 0}</b> · Удача: <b>${dig.luck}/100</b></p>`;
    if (stage.type === "event" || stage.type === "final") {
      const choices = (stage.choices || []).map(choice => `
        <button class="btn secondary" onclick="chooseMineEvent('${escapeJs(choice.key)}')">${escapeHtml(choice.label || "Выбрать")}</button>
      `).join("");
      return `<section class="panel">${header}
        <h3>${escapeHtml(stage.emoji || "❔")} ${escapeHtml(stage.title || "Событие")}</h3>
        <p>${escapeHtml(stage.text || "Выбери действие.")}</p>
        ${choices}
        <button class="btn danger" onclick="exitInteractiveDig()">💰 Забрать добычу и выйти</button>
      </section>`;
    }
    const cells = Array.isArray(stage) ? stage : (stage.cells || []);
    const used = new Set((dig.usedCells || []).map(Number));
    const emoji = { normal: "🟫", ore: "✨", hard: "🪨", roots: "🌿", unknown: "❓" };
    const cellHtml = cells.map((cell, index) => {
      const disabledCell = used.has(index);
      const revealed = cell.revealed ? `👁${emoji[cell.revealed] || "❓"}` : `${emoji[cell.kind] || "❓"}${index + 1}`;
      return `<button class="mine-cell ${disabledCell ? "used" : ""}" ${disabledCell ? "disabled" : ""} onclick="pickMineCell(${index}, this)">${revealed}</button>`;
    }).join("");
    const labels = { flashlight: "🔦 Фонарь", map: "🗺 Карта", dynamite: "🧨 Динамит", miner_hearing: "👂 Слух", magnet: "🧲 Магнит", cat_companion: "🐈 Компаньон" };
    const tools = (dig.tools || []).map(key => `<button class="btn secondary small-btn" onclick="useMineTool('${escapeJs(key)}')">${labels[key] || key}</button>`).join("");
    return `<section class="panel">${header}
      <p class="muted">Выбери клетку. Можно сначала использовать предмет разведки.</p>
      <div class="mine-grid">${cellHtml}</div>
      ${dig.preview ? `<p class="muted">🗺 Следующий ряд: ${escapeHtml(dig.preview)}</p>` : ""}
      ${tools ? `<div class="tool-grid">${tools}</div>` : ""}
      <button class="btn danger" onclick="exitInteractiveDig()">💰 Забрать добычу и выйти</button>
    </section>`;
  }

  function goldTicketHtml() {
    const game = state.ticketGame;
    if (!game && !state.goldenTickets) return "";
    if (!game) {
      return `<section class="panel">
        <div class="section-title"><h2>🎟️ Золотой билет</h2><span class="counter">${state.goldenTickets} шт.</span></div>
        <p class="muted">Три попытки. В трёх из девяти котиков спрятаны 10, 25 и 50 котоинов.</p>
        <button class="btn" onclick="startGoldTicket()">Играть</button>
      </section>`;
    }
    const cells = Array.from({ length: 9 }, (_, index) => {
      const opened = game.opened.includes(index);
      return `<button class="ticket-cell ${opened ? "opened" : ""}" ${opened ? "disabled" : ""}
        onclick="pickGoldTicket(${index}, this)">
        <span class="hammer">🔨</span>${opened ? '<span class="cell-prize">✓</span>' : catFigure(catForCell(index, 3))}
      </button>`;
    }).join("");
    return `<section class="panel" id="goldGamePanel">
      <div class="section-title"><h2>🎟️ Золотой билет</h2><span class="counter" id="goldAttempts">${game.attemptsLeft} попытки</span></div>
      <div class="ticket-grid">${cells}</div>
      <div class="game-result" id="goldResult" aria-live="polite"></div>
    </section>`;
  }

  function superGameHtml() {
    const game = state.superGame;
    if (!game) {
      const canStart = (state.goldenTickets || 0) >= 3 || (state.superPasses || 0) > 0;
      return `<section class="panel">
        <h2>🏆 Супер-игра 9×9</h2>
        <p class="muted">10 попыток: денежные призы от 50 до 250, пять призов по 5 котоинов и три сундука с особыми наградами.</p>
        <div>Билеты: <b>${state.goldenTickets || 0}/3</b></div>
        <button class="btn" ${canStart ? "" : "disabled"} onclick="startSuperGame()">Играть за 3 билета</button>
        <button class="btn secondary" onclick="buySuperGame()">Купить вход за 10 ⭐</button>
      </section>`;
    }
    const cells = Array.from({ length: 81 }, (_, index) => {
      const opened = game.opened.includes(index);
      return `<button class="super-cell ${opened ? "opened" : ""}" ${opened ? "disabled" : ""}
        onclick="pickSuper(${index}, this)">
        <span class="hammer">🔨</span>${opened ? '<span class="cell-prize">✓</span>' : catFigure(catForCell(index, 9))}
      </button>`;
    }).join("");
    return `<section class="panel" id="superGamePanel">
      <div class="section-title"><h2>🏆 Супер-игра</h2><span class="counter" id="superAttempts">${game.attemptsLeft} попыток</span></div>
      <div class="super-grid">${cells}</div>
      <div class="game-result" id="superResult" aria-live="polite"></div>
    </section>`;
  }

  function renderMine(scroll = true) {
    if (!state) return;
    setScreenHeader("mine");
    content.innerHTML = mineHtml();
    if (scroll) scrollToTop();
  }

  async function load() {
    const initialView = readStartParam();
    const intendedOwner = readStartOwner();
    setScreenHeader(["shop", "bag", "profile", "weather", "radio"].includes(initialView) ? initialView : "mine");
    try {
      state = await api("/miniapp/mine");
      if (intendedOwner && Number(state.userId) !== intendedOwner) {
        nameNode.textContent = "Чужая кнопка";
        content.innerHTML = '<section class="panel"><h2>Эта кнопка принадлежит другому пользователю</h2><p class="muted">Вызови свою команду «копай» или «сумка» в чате.</p></section>';
        return;
      }
      if (initialView === "shop") await showShop();
      else if (initialView === "bag") await showBag();
      else if (initialView === "profile") await showProfile();
      else if (initialView === "weather") await showWeather();
      else if (initialView === "radio") showRadio();
      else renderMine();
    } catch (error) {
      nameNode.textContent = "Ошибка загрузки";
      showError(error);
    }
  }

  async function registerMine() {
    if (busy) return;
    busy = true;
    try {
      state = await api("/miniapp/mine/register", { method: "POST" });
      renderMine();
    } catch (error) {
      showError(error);
    } finally {
      busy = false;
    }
  }

  async function selectShiftContract(contractKey) {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/mine/shift", {
        method: "POST", body: JSON.stringify({ contract_key: contractKey })
      });
      state = result.state;
      renderMine(false);
      showNotice("Сменное задание выбрано.");
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function startInteractiveDig(button) {
    if (busy) return;
    busy = true;
    if (button) button.disabled = true;
    try {
      const result = await api("/miniapp/mine/interactive/start", { method: "POST" });
      state = result.state;
      renderMine(false);
      showNotice(result.message || "Вылазка началась.");
    } catch (error) {
      showNotice(error.message);
    } finally {
      busy = false;
    }
  }

  async function pickMineCell(cell, button) {
    if (busy) return;
    busy = true;
    if (button) button.disabled = true;
    const overlay = showDigAnimation();
    try {
      const [result] = await Promise.all([
        api("/miniapp/mine/interactive/cell", {
          method: "POST", body: JSON.stringify({ cell })
        }),
        sleep(900)
      ]);
      state = result.state;
      renderMine(false);
      showNotice(result.message);
    } catch (error) {
      renderMine(false);
      showNotice(error.message);
    } finally {
      overlay.remove();
      busy = false;
    }
  }

  async function useMineTool(itemKey) {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/mine/interactive/tool", {
        method: "POST", body: JSON.stringify({ item_key: itemKey })
      });
      state = result.state;
      renderMine(false);
      showNotice(result.message);
    } catch (error) {
      showNotice(error.message);
    } finally {
      busy = false;
    }
  }

  async function chooseMineEvent(choiceKey) {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/mine/interactive/event", {
        method: "POST", body: JSON.stringify({ choice_key: choiceKey })
      });
      state = result.state;
      renderMine(false);
      showNotice(result.message);
    } catch (error) {
      showNotice(error.message);
    } finally {
      busy = false;
    }
  }

  async function exitInteractiveDig() {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/mine/interactive/exit", { method: "POST" });
      state = result.state;
      renderMine(false);
      showNotice(result.message);
    } catch (error) {
      showNotice(error.message);
    } finally {
      busy = false;
    }
  }

  async function startGoldTicket() {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/gold-ticket/start", { method: "POST" });
      state = result.state;
      renderMine(false);
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

  function updateGameUi(kind, attemptsLeft, message) {
    const attempts = document.getElementById(kind === "gold" ? "goldAttempts" : "superAttempts");
    const result = document.getElementById(kind === "gold" ? "goldResult" : "superResult");
    const coins = document.getElementById("mineCoins");
    if (attempts) attempts.textContent = attemptsLeft > 0 ? `${attemptsLeft} попыток` : "Игра завершена";
    if (result) result.textContent = message;
    if (coins && state) coins.textContent = state.coins;
    if (attemptsLeft <= 0) {
      const panel = document.getElementById(kind === "gold" ? "goldGamePanel" : "superGamePanel");
      if (panel) panel.querySelectorAll("button:not(:disabled)").forEach(item => { item.disabled = true; });
    }
  }

  async function pickGoldTicket(cell, button) {
    if (busy) return;
    busy = true;
    button.disabled = true;
    button.classList.add("breaking");
    try {
      const [result] = await Promise.all([
        api("/miniapp/gold-ticket/pick", {
          method: "POST", body: JSON.stringify({ cell })
        }),
        sleep(560)
      ]);
      button.classList.remove("breaking");
      button.innerHTML = `<span class="cell-prize">${result.prize ? `${result.prize} 🪙` : "Пусто"}</span>`;
      state = result.state;
      updateGameUi(
        "gold",
        result.attemptsLeft,
        result.prize ? `Найдено ${result.prize} котоинов!` : "Под котиком пусто."
      );
    } catch (error) {
      button.classList.remove("breaking");
      button.disabled = false;
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function startSuperGame() {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/super-game/start", { method: "POST" });
      state = result.state;
      renderMine(false);
      showNotice(result.source === "tickets" ? "Списано 3 золотых билета." : "Супер-игра открыта.");
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function buySuperGame() {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/super-game/invoice", { method: "POST" });
      if (telegram && telegram.openInvoice) {
        telegram.openInvoice(result.url, status => { if (status === "paid") load(); });
      } else {
        location.href = result.url;
      }
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function pickSuper(cell, button) {
    if (busy) return;
    busy = true;
    button.disabled = true;
    button.classList.add("breaking");
    try {
      const [result] = await Promise.all([
        api("/miniapp/super-game/pick", {
          method: "POST", body: JSON.stringify({ cell })
        }),
        sleep(560)
      ]);
      button.classList.remove("breaking");
      const cellResult = result.reward ? "Сундук" : result.coins ? `${result.coins} 🪙` : "Пусто";
      button.innerHTML = `<span class="cell-prize">${cellResult}</span>`;
      state = result.state;
      const messages = {
        mute30: "Сундук открыт: право выдать мут на 30 минут.",
        tag: "Сундук открыт: право выбрать себе тег в чате.",
        coins500: "Сундук открыт: 500 котоинов."
      };
      updateGameUi(
        "super",
        result.attemptsLeft,
        messages[result.reward] || (result.coins ? `Найдено ${result.coins} котоинов.` : "Клетка пустая.")
      );
    } catch (error) {
      button.classList.remove("breaking");
      button.disabled = false;
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function showBag() {
    setScreenHeader("bag");
    scrollToTop();
    try {
      const shop = await api("/miniapp/shop");
      const inventory = shop.inventory && shop.inventory.length
        ? shop.inventory.map((group, index) => {
          const rows = group.items.map(item => `
            <div class="inventory-row">
              <div class="inventory-row-main">
                <span>${escapeHtml(item.name)}</span>
                ${item.key === "tea" ? `<button class="btn inventory-use" onclick="useShopItem('tea')">Использовать</button>` : ""}
                ${item.giftable ? `<button class="btn inventory-use" onclick="showGiftTargets('${escapeHtml(item.key)}')">Подарить</button>` : ""}
                ${item.key === "super_mute30" ? `<button class="btn inventory-use" onclick="alert('В чате ответь на сообщение: супермут причина\\nИли напиши: супермут @username причина')">Как выдать</button>` : ""}
                ${item.key === "super_tag" ? `<button class="btn inventory-use" onclick="alert('В чате напиши: +кличка Твой тег\\nЛимит: 16 символов')">Как выбрать</button>` : ""}
              </div>
              <b>× ${item.quantity}</b>
            </div>`).join("");
          return `<details class="inventory-group" ${index === 0 ? "open" : ""}>
            <summary>
              <span>${escapeHtml(group.icon)} ${escapeHtml(group.title)}</span>
              <span class="inventory-group-count">${group.items.length}</span>
            </summary>
            <div class="inventory-list">${rows}</div>
          </details>`;
        }).join("")
        : `<div class="muted">Сумка пока пустая.</div>`;
      const merchantItems = ((shop.merchant && shop.merchant.items) || []).filter(item => Number(item.quantity || 0) > 0);
      const merchantRows = merchantItems.length
        ? merchantItems.map(item => `
            <div class="inventory-row">
              <div class="inventory-row-main">
                <span>${escapeHtml(item.emoji || "▪️")} ${escapeHtml(item.name)} × ${item.quantity}</span>
                <button class="btn inventory-use" onclick="sellMerchantResource('${escapeJs(item.key)}')">Продать</button>
              </div>
              <b>${item.price} 🪙/шт · ${item.total} 🪙</b>
            </div>`).join("")
        : `<div class="muted">Нет добычи для продажи. Ресурсы падают в ручной вылазке.</div>`;
      const merchant = `<section class="panel">
        <div class="section-title"><h2>🧑‍🌾 Торговец</h2><span class="counter">${shop.merchant ? shop.merchant.total : 0} 🪙</span></div>
        <p class="muted">${escapeHtml((shop.merchant && shop.merchant.nextPriceChangeText) || "Цены меняются каждый час.")}</p>
        <div class="inventory-list">${merchantRows}</div>
        <button class="btn" ${(shop.merchant && shop.merchant.total > 0) ? "" : "disabled"} onclick="sellMerchantResource()">Продать всю добычу</button>
      </section>`;
      content.innerHTML = `<section class="bag-screen">
        <div class="bag-summary">
          <h2>Снаряжение</h2>
          <div class="bag-balance">🪙 ${state.coins}</div>
        </div>
        ${state.rank && state.rank.level ? `<div class="rank-badge rank-${state.rank.level}">${rankEmblem(state.rank.level)} Значок сумки: ${escapeHtml(state.rank.name)} · скидка ${state.rank.level * 5}%</div>` : ""}
        ${rankCosmeticHtml(true)}
        <div class="bag-actions">
          <button class="btn" onclick="showShop()">Открыть магазин</button>
          <button class="btn secondary" onclick="renderMine()">Вернуться в шахту</button>
        </div>
        ${merchant}
        <div class="inventory">${inventory}</div>
      </section>`;
      scrollToTop();
    } catch (error) {
      showError(error);
    }
  }

  async function sellMerchantResource(itemKey = null) {
    if (busy) return;
    const question = itemKey ? "Продать этот ресурс по текущей цене?" : "Продать всю добычу по текущим ценам?";
    if (!confirm(question)) return;
    busy = true;
    try {
      const body = itemKey ? { item_key: itemKey } : {};
      const result = await api("/miniapp/merchant/sell", {
        method: "POST", body: JSON.stringify(body)
      });
      state = result.state;
      await showBag();
      showNotice(result.message || "Добыча продана.");
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function showShop(categoryKey = "") {
    setScreenHeader("shop");
    scrollToTop();
    try {
      const shop = await api("/miniapp/shop");
      renderShop(shop, categoryKey);
    } catch (error) {
      showError(error);
    }
  }

  function renderShop(shop, categoryKey = "") {
    setScreenHeader("shop");
    shopCategory = categoryKey || shopCategory || (shop.categories[0] && shop.categories[0].key);
    const category = shop.categories.find(item => item.key === shopCategory) || shop.categories[0];
    if (!category) {
      content.innerHTML = `<section class="panel">Магазин пока пуст.</section>`;
      return;
    }
    shopCategory = category.key;
    const tabs = shop.categories.map(item => `
      <button class="shop-tab ${item.key === shopCategory ? "active" : ""}" onclick="showShop('${item.key}')">
        ${escapeHtml(item.title)}
      </button>`).join("");
    const products = category.items.map(item => {
      const status = item.owned
        ? `<div class="owned">Уже куплено</div>`
        : item.quantity ? `<div class="owned">В сумке: ${item.quantity}</div>` : `<div class="muted">Доступно к покупке</div>`;
      const requirement = item.requirement
        ? `<div class="muted">Нужно: ${escapeHtml(item.requirementName || item.requirement)}</div>` : "";
      const isStarItem = Number(item.starPrice || 0) > 0;
      const buy = item.owned ? "" : `
        <button class="btn shop-buy" ${item.canBuy ? "" : "disabled"} onclick="${isStarItem ? `buyStarShop('${item.key}')` : `buyShop('${item.key}')`}">
          Купить
        </button>`;
      return `<article class="product">
        <div class="product-name">${escapeHtml(item.name)}</div>
        <div class="price">${isStarItem ? `${item.starPrice} ⭐` : `${item.price} 🪙${item.discount ? ` <s>${item.basePrice}</s>` : ""}`}</div>
        <div class="description">${escapeHtml(item.description)}</div>
        <div class="product-meta">${status}${item.discount ? `<div class="owned">Скидка ранга: ${item.discount}%</div>` : ""}${requirement}</div>
        ${buy}
      </article>`;
    }).join("");
    content.innerHTML = `<section class="shop-screen">
      <div class="shop-hero">
        <div class="shop-hero-copy">
          <div class="shop-kicker">Лавка шахтёра</div>
          <h2>${escapeHtml(category.title)}</h2>
          <p>Шахта, профиль, подарки и отношения — выбирай, куда тратить котоины.</p>
        </div>
        <div class="shop-coins">🪙 ${shop.coins}</div>
      </div>
      <div class="shop-toolbar"><div class="shop-tabs">${tabs}</div></div>
      <div class="shop-products">${products}</div>
      <div class="shop-back"><button class="btn secondary" onclick="showBag()">Назад в сумку</button></div>
    </section>`;
    enableHorizontalWheelScroll(".shop-tabs");
    scrollToTop();
  }

  async function buyShop(itemKey) {
    if (busy || !confirm("Купить этот предмет за котоины?")) return;
    busy = true;
    try {
      const result = await api("/miniapp/shop/buy", {
        method: "POST", body: JSON.stringify({ item_key: itemKey })
      });
      state = result.state;
      renderShop(result.shop, shopCategory);
      showNotice("Покупка выполнена. Предмет добавлен в сумку.");
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function buyStarShop(itemKey) {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/shop/star-invoice", {
        method: "POST", body: JSON.stringify({ item_key: itemKey })
      });
      if (telegram && telegram.openInvoice) {
        telegram.openInvoice(result.url, status => {
          if (status === "paid") {
            showShop(shopCategory);
            showNotice("Оплата прошла. Предмет добавится в сумку после обработки платежа.");
          }
        });
      } else {
        location.href = result.url;
      }
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function useShopItem(itemKey) {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/miniapp/shop/use", {
        method: "POST", body: JSON.stringify({ item_key: itemKey })
      });
      state = result.state;
      await showBag();
      showNotice(result.message || "Предмет использован.");
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  async function showGiftTargets(itemKey) {
    setScreenHeader("bag");
    scrollToTop();
    content.innerHTML = `<section class="panel muted">Ищу друзей и пару для подарка...</section>`;
    try {
      const data = await api(`/miniapp/shop/gift-targets?item_key=${encodeURIComponent(itemKey)}`);
      const item = data.item || {};
      const targets = data.targets || [];
      const hint = data.targetKind === "partner"
        ? "Этот подарок можно отправить только текущей паре."
        : "Выбери друга, которому отправить подарок.";
      const targetRows = targets.length ? targets.map(target => `
        <button class="btn secondary" onclick="sendGift('${escapeHtml(itemKey)}', ${Number(target.id)})">
          ${escapeHtml(target.fullName || "Игрок")}${target.username ? ` · @${escapeHtml(target.username)}` : ""}
        </button>`).join("") : `<p class="muted">Подходящих получателей пока нет. Для подарков нужны друзья/пара, которые уже зарегистрированы в шахте.</p>`;
      content.innerHTML = `<section class="panel">
        <h2>Подарить</h2>
        <p><b>${escapeHtml(item.name || itemKey)}</b> · в сумке: <b>${Number(item.quantity || 0)}</b></p>
        <p class="muted">${hint}</p>
        <div class="shift-options">${targetRows}</div>
        <button class="btn secondary" onclick="showBag()">Назад в сумку</button>
      </section>`;
      scrollToTop();
    } catch (error) {
      showError(error);
    }
  }

  async function sendGift(itemKey, targetUserId) {
    if (busy || !confirm("Отправить этот подарок?")) return;
    busy = true;
    try {
      const result = await api("/miniapp/shop/gift", {
        method: "POST",
        body: JSON.stringify({ item_key: itemKey, target_user_id: targetUserId })
      });
      state = result.state;
      await showBag();
      showNotice(result.message || "Подарок отправлен.");
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  setInterval(() => {
    if (state && state.cooldownUntil && new Date(state.cooldownUntil).getTime() <= Date.now()) {
      state.cooldownUntil = null;
      renderMine();
    }
  }, 15000);

  load();
</script>
</body>
</html>
"""
