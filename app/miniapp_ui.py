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
      --panel-2: #20364b;
      --line: #2b455e;
      --text: #f5f7fa;
      --muted: #aeb9c6;
      --accent: #2794d2;
      --accent-2: #e5a64a;
      --ok: #5ecb83;
      --danger: #d95c62;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }
    body {
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      padding: max(16px, env(safe-area-inset-top)) 16px max(24px, env(safe-area-inset-bottom));
    }
    button { font: inherit; }
    main { width: min(100%, 560px); margin: 0 auto; }
    .top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .top-actions { display: flex; align-items: center; gap: 8px; }
    .top-profile {
      width: auto;
      min-height: 38px;
      margin: 0;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      color: var(--text);
      font-weight: 800;
      white-space: nowrap;
    }
    h1, h2, p { margin-top: 0; }
    h1 { margin-bottom: 2px; font-size: 34px; letter-spacing: 0; }
    h2 { margin-bottom: 10px; font-size: 23px; letter-spacing: 0; }
    .muted { color: var(--muted); }
    .panel {
      margin-top: 14px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 16px; }
    .stat {
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
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
    .rank-card .rank-emblem { display:grid; place-items:center; width:42px; height:42px; border-radius:8px; background: color-mix(in srgb, var(--rank-color, #678fb2) 28%, #07111c); font-size:26px; }
    .rank-card.rank-1, .rank-badge.rank-1 { --rank-color:#678fb2; border-color:#678fb2; }
    .rank-card.rank-2, .rank-badge.rank-2 { --rank-color:#62a879; border-color:#62a879; }
    .rank-card.rank-3, .rank-badge.rank-3 { --rank-color:#ce9b49; border-color:#ce9b49; }
    .rank-card.rank-4, .rank-badge.rank-4 { --rank-color:#bc6f88; border-color:#bc6f88; }
    .rank-badge { display:inline-flex; align-items:center; gap:7px; margin-top:10px; padding:7px 10px; border:1px solid var(--line); border-radius:8px; background: color-mix(in srgb, var(--rank-color, #678fb2) 18%, var(--panel)); font-size:13px; font-weight:800; }
    .utility-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
    .utility-actions .btn { min-height: 46px; margin: 0; }
    .mini-form { display: grid; gap: 8px; margin-top: 12px; }
    .mini-form input {
      width: 100%;
      min-height: 44px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0f1c2a;
      color: var(--text);
      font: inherit;
    }
    .mini-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .mini-row .btn { min-height: 44px; margin: 0; }
    .profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    .profile-card { padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
    .profile-card b { display: block; margin-top: 4px; font-size: 18px; overflow-wrap: anywhere; }
    .profile-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
    .profile-actions .btn { margin: 0; min-height: 44px; }
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
      border-radius: 8px;
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
      border-radius: 8px;
      background: var(--accent);
      color: white;
      font-weight: 750;
      cursor: pointer;
    }
    .btn.secondary { background: var(--panel-2); }
    .btn:disabled { opacity: .45; cursor: default; }
    .depth { padding: 18px 0; text-align: center; font-size: 48px; font-weight: 850; }
    .meter { height: 12px; overflow: hidden; border-radius: 7px; background: #09111c; }
    .fill { height: 100%; background: var(--accent); transition: width .25s ease; }
    .notice { white-space: pre-line; border-color: #4b6f91; }
    .section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .counter { white-space: nowrap; font-weight: 800; }
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
      scrollbar-width: none;
      scroll-snap-type: x proximity;
    }
    .shop-tabs::-webkit-scrollbar { display: none; }
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
<main>
  <header class="top">
    <div>
      <h1 id="screen-title">⛏️ Шахта</h1>
      <div id="name" class="muted">Загрузка...</div>
    </div>
    <div class="top-actions">
      <button class="top-profile" onclick="showProfile()">Профиль</button>
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
  const radioPlayer = document.getElementById("radioPlayer");
  let state = null;
  let busy = false;
  let shopCategory = "";

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
    document.body.dataset.view = view;
    if (view === "shop") {
      screenTitle.textContent = "🛒 Магазин";
      nameNode.textContent = "Лавка шахтёра";
    } else if (view === "bag") {
      screenTitle.textContent = "🎒 Сумка";
      nameNode.textContent = "Инвентарь шахтёра";
    } else if (view === "profile") {
      screenTitle.textContent = "👤 Профиль";
      nameNode.textContent = "MonkeyDin";
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
  }

  function scrollToTop() {
    window.scrollTo(0, 0);
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

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
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

  function renderProfile(profile) {
    setScreenHeader("profile");
    const user = profile.user || {};
    const premium = profile.premium || {};
    const plan = premium.plan || {};
    const mine = profile.mine || {};
    const premiumText = premium.active ? (plan.title || "Premium активен") : "не активен";
    const groupedItems = {};
    (mine.activeItems || []).slice(0, 18).forEach(item => {
      const key = item.group || "consumable";
      if (!groupedItems[key]) groupedItems[key] = { title: item.groupTitle || "Припасы", items: [] };
      groupedItems[key].items.push(item);
    });
    const groupOrder = ["collection", "permanent", "paid", "tickets", "consumable"];
    const itemGroupsHtml = groupOrder.filter(key => groupedItems[key]).map(key => {
      const group = groupedItems[key];
      const chips = group.items.map(item => `<span class="inventory-chip ${escapeHtml(item.group || "consumable")}">${escapeHtml(item.name)}${item.quantity > 1 ? ` <b>×${item.quantity}</b>` : ""}</span>`).join("");
      return `<div class="inventory-chip-group">
        <div class="inventory-chip-title">${escapeHtml(group.title)}</div>
        <div class="inventory-chips">${chips}</div>
      </div>`;
    }).join("");
    const rareAchievements = (mine.rareAchievements || []).slice(0, 5).map(item => `
      <div class="achievement-card ${escapeHtml(item.rarity || "common")}">
        <b>${escapeHtml(item.name)}</b>
        <div class="achievement-rarity">${escapeHtml(item.rarityTitle || "Обычное")}</div>
      </div>
    `).join("");
    content.innerHTML = `<section class="panel">
      <h2>${escapeHtml(user.fullName || "Профиль")}</h2>
      <div class="muted">${user.username ? `@${escapeHtml(user.username)}` : "username не указан"}</div>
      <div class="profile-grid">
        <div class="profile-card">Premium<b>${escapeHtml(premiumText)}</b></div>
        <div class="profile-card">Ранг<b>${escapeHtml(mine.rank || "Новичок")}</b></div>
        <div class="profile-card">Котоины<b>${mine.coins || 0}</b></div>
        <div class="profile-card">Глубина<b>${mine.totalDepth || 0} м</b></div>
        <div class="profile-card">Уровень<b>${mine.level || 0}</b></div>
        <div class="profile-card">Удача<b>${mine.luck || 0}/100</b></div>
      </div>
      <div class="profile-actions">
        <button class="btn secondary" onclick="showFriendsInfo()">Друзья</button>
        <button class="btn secondary" onclick="showBag()">Сумка</button>
      </div>
    </section>
    <section class="panel">
      <h2>Шахта</h2>
      <p class="muted">Рекорд: <b>${mine.bestSessionDepth || 0} м</b> · Серия: <b>${mine.streak || 0}</b> · Маршрут: <b>${escapeHtml(mine.route || "не выбран")}</b></p>
      <p class="muted">Достижения: <b>${mine.achievementsTotal || 0}/${mine.achievementsKnown || 0}</b></p>
    </section>
    ${itemGroupsHtml ? `<section class="panel"><h2>Инвентарь</h2><div class="inventory-groups">${itemGroupsHtml}</div>${(mine.activeItemsTotal || 0) > 18 ? `<p class="muted">И ещё ${mine.activeItemsTotal - 18} предметов в сумке.</p>` : ""}</section>` : ""}
    ${rareAchievements ? `<section class="panel"><h2>Редчайшие достижения</h2><div class="achievement-showcase">${rareAchievements}</div></section>` : ""}
    <section class="panel"><button class="btn secondary" style="margin:0" onclick="renderMine()">Назад в шахту</button></section>`;
    scrollToTop();
  }

  function showFriendsInfo() {
    setScreenHeader("profile");
    content.innerHTML = `<section class="panel">
      <h2>Друзья</h2>
      <p class="muted">Дружба сейчас привязана к конкретному чату Telegram: в разных группах список может быть разным.</p>
      <div class="achievement-showcase">
        <div class="achievement-card rare"><b>Как добавить</b><div class="muted">В группе открой профиль участника ответом на его сообщение или через профиль в меню пользователя, затем нажми «Добавить в друзья».</div></div>
        <div class="achievement-card epic"><b>Идея для лички</b><div class="muted">Команда вида <code>лс @ник текст</code>: бот доставляет приватную записку, если оба участника уже запускали бота и состоят в этом чате.</div></div>
        <div class="achievement-card legendary"><b>Идея для Mini App</b><div class="muted">Открывать Mini App из группы с chat_id, тогда здесь можно показать друзей, пару, заявки и быстрые действия.</div></div>
      </div>
      <button class="btn secondary" onclick="showProfile()">Назад к профилю</button>
    </section>`;
    scrollToTop();
  }

  async function showProfile() {
    setScreenHeader("profile");
    content.innerHTML = `<section class="panel muted">Загружаю профиль MonkeyDin...</section>`;
    try {
      renderProfile(await api("/miniapp/profile"));
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
        <p class="muted">Прогресс: <b>${escapeHtml(status)}</b> · награда: <b>${selected.reward}</b> котоинов.</p>
      </section>`;
    }
    const options = (shift.options || []).map(item => `
      <button class="btn secondary" onclick="selectShiftContract('${item.key}')">
        ${escapeHtml(item.name)} · +${item.reward} 🪙
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
    const depth = state.sessionDepth || 0;
    const disabled = isCoolingDown();
    const cooldown = disabled
      ? `Копать снова можно: ${new Date(state.cooldownUntil).toLocaleString()}`
      : "Одно нажатие проверяет один следующий метр.";
    return `
      <div class="stats">
        <div class="stat">🪙<b id="mineCoins">${state.coins}</b></div>
        <div class="stat">🍀<b>${state.luck}/100</b></div>
        <div class="stat">🏆<b>${state.record} м</b></div>
      </div>
      ${utilityActionsHtml()}
      ${shiftContractHtml()}
      <section class="panel">
        <div class="muted">Текущая вылазка</div>
        <div class="depth">${depth}/10 м</div>
        <div class="meter"><div class="fill" style="width:${depth * 10}%"></div></div>
        <button class="btn" ${disabled ? "disabled" : ""} onclick="digOneMeter(this)">⛏️ Копать следующий метр</button>
        <div class="muted" style="margin-top:10px">${escapeHtml(cooldown)}</div>
      </section>
      ${goldTicketHtml()}
      ${superGameHtml()}
      <section class="panel">Уровень <b>${state.level}</b> · XP <b>${state.xp}</b> · серия <b>${state.streak}</b></section>
      <section class="panel">
        <button class="btn secondary" style="margin:0" onclick="showBag()">Сумка</button>
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

  async function digOneMeter(button) {
    if (busy) return;
    busy = true;
    button.disabled = true;
    button.textContent = "⛏️ Копаем...";
    const overlay = showDigAnimation();
    try {
      const [result] = await Promise.all([
        api("/miniapp/mine/dig", { method: "POST" }),
        sleep(1150)
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
        <div class="inventory">${inventory}</div>
      </section>`;
      scrollToTop();
    } catch (error) {
      showError(error);
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
          <p>Снаряжение и припасы для новых вылазок.</p>
        </div>
        <div class="shop-coins">🪙 ${shop.coins}</div>
      </div>
      <div class="shop-toolbar"><div class="shop-tabs">${tabs}</div></div>
      <div class="shop-products">${products}</div>
      <div class="shop-back"><button class="btn secondary" onclick="showBag()">Назад в сумку</button></div>
    </section>`;
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
