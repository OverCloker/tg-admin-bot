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
      position: relative;
      display: block;
      width: 58%;
      aspect-ratio: 1;
      transform: rotateX(8deg) rotateY(-7deg);
      filter: drop-shadow(0 8px 4px #0008);
    }
    .cat-face {
      position: absolute;
      inset: 13% 4% 2%;
      z-index: 2;
      border-radius: 48% 48% 44% 44%;
      background: radial-gradient(circle at 37% 34%, #fff4ce 0 5%, transparent 6%),
                  linear-gradient(145deg, #dca75d, #8b582b);
      border: 2px solid #f1c57f;
      box-shadow: inset -7px -9px 10px #5b321e80, inset 7px 5px 7px #ffe0a750;
    }
    .cat-ear {
      position: absolute;
      top: 1%;
      z-index: 1;
      width: 38%;
      height: 42%;
      background: linear-gradient(135deg, #dca75d, #71401f);
      border: 2px solid #efc27a;
      transform: rotate(45deg);
    }
    .cat-ear.left { left: 5%; }
    .cat-ear.right { right: 5%; }
    .cat-eye {
      position: absolute;
      top: 39%;
      width: 13%;
      height: 18%;
      border-radius: 50%;
      background: #d8ef5e;
      box-shadow: inset 0 0 0 3px #253014;
    }
    .cat-eye.left { left: 25%; }
    .cat-eye.right { right: 25%; }
    .cat-nose {
      position: absolute;
      left: 45%;
      top: 61%;
      width: 12%;
      height: 9%;
      border-radius: 60% 60% 70% 70%;
      background: #4b241f;
    }
    .super-cell .cat-figure { width: 72%; }
    .super-cell .cat-face,
    .super-cell .cat-ear { border-width: 1px; }
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
    .inventory-row b { flex: 0 0 auto; color: #dbe7f2; }
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
      width: 92px;
      height: 74px;
      margin: 2px auto 17px;
      filter: drop-shadow(0 12px 8px #0008);
    }
    .chest-base, .chest-lid {
      position: absolute;
      left: 8px;
      width: 76px;
      border: 4px solid #5d3515;
      background: linear-gradient(90deg, #7c461d, #d49b42 48%, #754019);
      box-shadow: inset 0 0 0 4px #f1c16455;
    }
    .chest-base { bottom: 0; height: 45px; border-radius: 4px 4px 10px 10px; }
    .chest-lid {
      top: 10px;
      height: 31px;
      border-radius: 34px 34px 5px 5px;
      transform-origin: 50% 100%;
      animation: chest-open .9s cubic-bezier(.25,.8,.25,1) forwards;
    }
    .chest-light {
      position: absolute;
      left: 20px;
      top: 27px;
      width: 52px;
      height: 34px;
      border-radius: 50%;
      background: #ffe27e;
      filter: blur(12px);
      opacity: 0;
      animation: treasure-light 1s .35s ease-out forwards;
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
      65%, 100% { transform: translateY(-19px) rotateX(65deg); }
    }
    @keyframes treasure-light {
      to { opacity: .95; transform: scale(1.5); }
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
    <button class="btn secondary" style="width:auto;margin:0" type="button" id="close">Закрыть</button>
  </header>
  <div id="content"></div>
</main>
<script>
  const telegram = window.Telegram && window.Telegram.WebApp;
  const content = document.getElementById("content");
  const nameNode = document.getElementById("name");
  const screenTitle = document.getElementById("screen-title");
  let state = null;
  let busy = false;
  let shopCategory = "";

  function setScreenHeader(view) {
    document.body.dataset.view = view;
    if (view === "shop") {
      screenTitle.textContent = "🛒 Магазин";
      nameNode.textContent = "Лавка шахтёра";
    } else if (view === "bag") {
      screenTitle.textContent = "🎒 Сумка";
      nameNode.textContent = "Инвентарь шахтёра";
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

  document.getElementById("close").addEventListener("click", () => {
    if (telegram) telegram.close();
  });

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
          <span class="chest-base"></span>
          <span class="chest-lid"></span>
        </div>
        <div>${escapeHtml(cleanText)}</div>`;
    } else {
      node.textContent = cleanText;
    }
    content.prepend(node);
  }

  function catFigure() {
    return `<span class="cat-figure" aria-hidden="true">
      <span class="cat-ear left"></span>
      <span class="cat-ear right"></span>
      <span class="cat-face">
        <span class="cat-eye left"></span>
        <span class="cat-eye right"></span>
        <span class="cat-nose"></span>
      </span>
    </span>`;
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

  function readStartParam() {
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
    if (urlParam) return urlParam.trim().toLowerCase();

    const encodedInitData = query.get("tgWebAppData") || hash.get("tgWebAppData");
    if (encodedInitData) {
      try {
        const nestedParam = new URLSearchParams(decodeURIComponent(encodedInitData)).get("start_param");
        if (nestedParam) return nestedParam.trim().toLowerCase();
      } catch (_) {
        // Fall through to Telegram's parsed launch data.
      }
    }

    const direct =
      (telegram && telegram.initDataUnsafe && telegram.initDataUnsafe.start_param) ||
      (telegram && telegram.initData && new URLSearchParams(telegram.initData).get("start_param"));
    return direct ? direct.trim().toLowerCase() : "";
  }

  function isCoolingDown() {
    return state && state.cooldownUntil &&
      new Date(state.cooldownUntil).getTime() > Date.now() &&
      !state.inSession;
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
        <div class="stat">🪙<b>${state.coins}</b></div>
        <div class="stat">🍀<b>${state.luck}/100</b></div>
        <div class="stat">🏆<b>${state.record} м</b></div>
      </div>
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
        <span class="hammer">🔨</span>${opened ? '<span class="cell-prize">✓</span>' : catFigure()}
      </button>`;
    }).join("");
    return `<section class="panel">
      <div class="section-title"><h2>🎟️ Золотой билет</h2><span class="counter">${game.attemptsLeft} попытки</span></div>
      <div class="ticket-grid">${cells}</div>
    </section>`;
  }

  function superGameHtml() {
    const game = state.superGame;
    if (!game) {
      const canStart = (state.goldenTickets || 0) >= 3 || (state.superPasses || 0) > 0;
      return `<section class="panel">
        <h2>🏆 Супер-игра 9×9</h2>
        <p class="muted">10 попыток, денежные призы от 50 до 250 котоинов и один сундук с особой наградой.</p>
        <div>Билеты: <b>${state.goldenTickets || 0}/3</b></div>
        <button class="btn" ${canStart ? "" : "disabled"} onclick="startSuperGame()">Играть за 3 билета</button>
        <button class="btn secondary" onclick="buySuperGame()">Купить вход за 10 ⭐</button>
      </section>`;
    }
    const cells = Array.from({ length: 81 }, (_, index) => {
      const opened = game.opened.includes(index);
      return `<button class="super-cell ${opened ? "opened" : ""}" ${opened ? "disabled" : ""}
        onclick="pickSuper(${index}, this)">
        <span class="hammer">🔨</span>${opened ? '<span class="cell-prize">✓</span>' : catFigure()}
      </button>`;
    }).join("");
    return `<section class="panel">
      <div class="section-title"><h2>🏆 Супер-игра</h2><span class="counter">${game.attemptsLeft} попыток</span></div>
      <div class="super-grid">${cells}</div>
    </section>`;
  }

  function renderMine() {
    if (!state) return;
    setScreenHeader("mine");
    content.innerHTML = mineHtml();
    scrollToTop();
  }

  async function load() {
    const initialView = readStartParam();
    setScreenHeader(initialView === "shop" ? "shop" : initialView === "bag" ? "bag" : "mine");
    try {
      state = await api("/miniapp/mine");
      if (initialView === "shop") await showShop();
      else if (initialView === "bag") await showBag();
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
      renderMine();
      showNotice(result.message);
    } catch (error) {
      renderMine();
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
      renderMine();
    } catch (error) {
      alert(error.message);
    } finally {
      busy = false;
    }
  }

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

  async function pickGoldTicket(cell, button) {
    if (busy) return;
    busy = true;
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
      await sleep(700);
      state = result.state;
      renderMine();
      showNotice(result.prize ? `Найдено ${result.prize} котоинов!` : "Под котиком пусто.");
    } catch (error) {
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
      renderMine();
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
      await sleep(700);
      state = result.state;
      renderMine();
      const messages = {
        mute30: "Сундук открыт: право выдать мут на 30 минут.",
        tag: "Сундук открыт: право выбрать себе тег в чате.",
        coins500: "Сундук открыт: 500 котоинов."
      };
      showNotice(messages[result.reward] || (result.coins ? `Найдено ${result.coins} котоинов.` : "Клетка пустая."), Boolean(result.reward));
    } catch (error) {
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
              <span>${escapeHtml(item.name)}</span>
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
      const buy = item.owned ? "" : `
        <button class="btn shop-buy" ${item.canBuy ? "" : "disabled"} onclick="buyShop('${item.key}')">
          Купить
        </button>`;
      return `<article class="product">
        <div class="product-name">${escapeHtml(item.name)}</div>
        <div class="price">${item.price} 🪙</div>
        <div class="description">${escapeHtml(item.description)}</div>
        <div class="product-meta">${status}${requirement}</div>
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
