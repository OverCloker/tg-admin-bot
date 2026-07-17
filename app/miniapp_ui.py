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
    .inventory { display: grid; gap: 7px; margin-top: 12px; }
    .inventory-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid var(--line);
    }
    .shop-screen {
      min-height: calc(100vh - 32px);
      margin-top: 14px;
      padding: 16px;
      border-radius: 8px;
      background: linear-gradient(#120d09b8, #120d09e8), url("/miniapp/shop-bg.png") center top / cover;
    }
    .shop-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .shop-coins {
      padding: 8px 10px;
      border: 1px solid #d49a50;
      border-radius: 8px;
      background: #15100cd9;
      font-weight: 800;
      white-space: nowrap;
    }
    .shop-tabs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin: 14px 0; }
    .shop-tab {
      min-height: 43px;
      padding: 8px;
      border: 1px solid #c98e49;
      border-radius: 8px;
      background: #241a14e8;
      color: white;
      font-weight: 700;
    }
    .shop-tab.active { background: #a9652d; }
    .product {
      margin-top: 9px;
      padding: 13px;
      border: 1px solid #b57c42;
      border-radius: 8px;
      background: #16283bed;
    }
    .product-head { display: flex; justify-content: space-between; gap: 10px; }
    .product-name { font-weight: 800; }
    .price { color: #ffd37d; font-weight: 800; white-space: nowrap; }
    .description { margin-top: 6px; color: #d0d8e1; font-size: 14px; line-height: 1.4; }
    .owned { margin-top: 7px; color: var(--ok); font-size: 14px; }
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
      <h1>⛏️ Шахта</h1>
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
  let state = null;
  let busy = false;
  let shopCategory = "";

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
    const direct =
      (telegram && telegram.initDataUnsafe && telegram.initDataUnsafe.start_param) ||
      (telegram && telegram.initData && new URLSearchParams(telegram.initData).get("start_param"));
    if (direct) return direct;

    const query = new URLSearchParams(location.search);
    const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
    const launchParam =
      query.get("tgWebAppStartParam") ||
      hash.get("tgWebAppStartParam") ||
      query.get("start_param") ||
      hash.get("start_param") ||
      query.get("startapp") ||
      hash.get("startapp") ||
      query.get("view") ||
      hash.get("view");
    if (launchParam) return launchParam;

    const encodedInitData = query.get("tgWebAppData") || hash.get("tgWebAppData");
    if (!encodedInitData) return "";
    try {
      return new URLSearchParams(decodeURIComponent(encodedInitData)).get("start_param") || "";
    } catch (_) {
      return "";
    }
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
    nameNode.textContent = state.registered ? state.name : "Новая вылазка";
    content.innerHTML = mineHtml();
  }

  async function load() {
    try {
      state = await api("/miniapp/mine");
      const initialView = readStartParam();
      if (initialView === "shop" && state.registered) await showShop();
      else if (initialView === "bag" && state.registered) await showBag();
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
    try {
      const shop = await api("/miniapp/shop");
      const names = {};
      shop.categories.forEach(category => category.items.forEach(item => { names[item.key] = item.name; }));
      const entries = Object.entries(state.items || {}).filter(([, quantity]) => quantity > 0);
      const inventory = entries.length
        ? entries.map(([key, quantity]) => `<div class="inventory-row"><span>${escapeHtml(names[key] || key)}</span><b>× ${quantity}</b></div>`).join("")
        : `<div class="muted">Сумка пока пустая.</div>`;
      content.innerHTML = `<section class="panel">
        <div class="section-title"><h2>Сумка шахтёра</h2><span class="counter">🪙 ${state.coins}</span></div>
        <div class="inventory">${inventory}</div>
        <button class="btn" onclick="showShop()">Магазин</button>
        <button class="btn secondary" onclick="renderMine()">Назад к шахте</button>
      </section>`;
    } catch (error) {
      showError(error);
    }
  }

  async function showShop(categoryKey = "") {
    try {
      const shop = await api("/miniapp/shop");
      renderShop(shop, categoryKey);
    } catch (error) {
      showError(error);
    }
  }

  function renderShop(shop, categoryKey = "") {
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
        : item.quantity ? `<div class="owned">В сумке: ${item.quantity}</div>` : "";
      const requirement = item.requirement
        ? `<div class="muted" style="margin-top:6px">Нужно: ${escapeHtml(item.requirement)}</div>` : "";
      const buy = item.owned ? "" : `
        <button class="btn" ${item.canBuy ? "" : "disabled"} onclick="buyShop('${item.key}')">
          Купить за ${item.price} 🪙
        </button>`;
      return `<article class="product">
        <div class="product-head">
          <div class="product-name">${escapeHtml(item.name)}</div>
          <div class="price">${item.price} 🪙</div>
        </div>
        <div class="description">${escapeHtml(item.description)}</div>
        ${status}${requirement}${buy}
      </article>`;
    }).join("");
    content.innerHTML = `<section class="shop-screen">
      <div class="shop-head"><h2>Магазин шахты</h2><div class="shop-coins">🪙 ${shop.coins}</div></div>
      <div class="shop-tabs">${tabs}</div>
      ${products}
      <button class="btn secondary" onclick="showBag()">Назад в сумку</button>
    </section>`;
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
