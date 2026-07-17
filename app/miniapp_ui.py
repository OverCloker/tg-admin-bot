"""Mobile-first Telegram Mini App UI for the mine and golden-ticket game."""

MINI_APP_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Шахта</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif;background:#0b111b;color:#f4f7fb}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--tg-bg,#0b111b);color:var(--tg-text,#f4f7fb)}
main{max-width:520px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center}
h1{font-size:28px;margin:0}.muted{color:#9ba8b8}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}
.panel,.stat{background:#172434;border:1px solid #26394d;border-radius:14px;padding:14px;margin-top:12px}
.stat b{display:block;font-size:19px;margin-top:4px}.depth{text-align:center;font-size:44px;font-weight:800;padding:18px}
.meter{height:10px;background:#0e1722;border-radius:9px;overflow:hidden}.fill{height:100%;background:#45b9ef}
.btn{width:100%;border:0;border-radius:12px;padding:14px;margin-top:12px;background:#268bd2;color:#fff;font-size:17px;font-weight:700}
.btn.secondary{background:#26394d;font-size:14px;padding:9px;width:auto;margin:0}.btn:disabled{opacity:.45}
.notice{white-space:pre-line;line-height:1.45}.ticket-title{font-size:21px;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.cell{aspect-ratio:1;border:1px solid #3b5872;border-radius:12px;background:#233a51;color:#fff;font-size:24px;font-weight:800}.cell.opened{background:#30495d;color:#aebdcc}.cell:disabled{opacity:1}
</style>
</head>
<body><main>
<div class="top"><div><h1>⛏️ Шахта</h1><div class="muted" id="name">Загрузка...</div></div><button class="btn secondary" onclick="tg&&tg.close()">Закрыть</button></div>
<div id="content"></div>
</main>
<script>
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){tg.ready();tg.expand()}
const H=()=>({'X-Telegram-Init-Data':tg?tg.initData:''});let s=null,busy=false;
async function api(path,opts={}){const r=await fetch(path,Object.assign({},opts,{headers:Object.assign({},H(),opts.headers||{}, {'Content-Type':'application/json'})}));const d=await r.json().catch(()=>({detail:'Ошибка сервера'}));if(!r.ok)throw Error(d.detail||'Ошибка запроса');return d}
function note(text){const n=document.createElement('section');n.className='panel notice';n.textContent=text;content.prepend(n)}
function ticketHtml(){if(!s.goldenTickets&&!s.ticketGame)return '';let g=s.ticketGame;let html='<section class="panel"><div class="ticket-title">🎟️ Золотой билет</div><div class="muted">Билетов: '+s.goldenTickets+'</div>';if(!g){html+='<div class="notice" style="margin-top:8px">Три попытки. На поле спрятаны призы: 10, 25 и 50 котоинов.</div><button class="btn" onclick="startTicket()">Сыграть билет</button></section>';return html}html+='<div class="notice" style="margin-top:8px">Осталось попыток: '+g.attemptsLeft+'</div><div class="grid">';for(let i=0;i<9;i++){const opened=g.opened.includes(i);html+='<button class="cell '+(opened?'opened':'')+'" '+(opened?'disabled':'')+' onclick="pickTicket('+i+')">'+(opened?'✓':'?')+'</button>'}return html+'</div></section>'}
function render(){if(!s)return;document.getElementById('name').textContent=s.registered?s.name:'Новая вылазка';if(!s.registered){content.innerHTML='<section class="panel"><div class="depth">⛏️</div><div>Зарегистрируйтесь, чтобы начать общую шахту. Прогресс и котоины сохраняются в боте.</div><button class="btn" onclick="reg()">Начать игру</button></section>';return}const d=s.sessionDepth||0;const disabled=s.cooldownUntil&&!s.inSession;content.innerHTML='<div class="stats"><div class="stat">🪙<b>'+s.coins+'</b></div><div class="stat">🍀<b>'+s.luck+'/100</b></div><div class="stat">🏆<b>'+s.record+' м</b></div></div><section class="panel"><div class="muted">Текущая вылазка</div><div class="depth">'+d+'/10 м</div><div class="meter"><div class="fill" style="width:'+(d*10)+'%"></div></div><button class="btn" '+(disabled?'disabled':'')+' onclick="dig()">⛏️ Копать следующий метр</button><div class="muted" style="margin-top:9px">'+(disabled?'Кулдаун: '+new Date(s.cooldownUntil).toLocaleString():'Каждое нажатие проверяет один метр. Шансы те же, что в боте.')+'</div></section>'+ticketHtml()+'<section class="panel">Уровень '+s.level+' · XP '+s.xp+' · серия '+s.streak+'</section>'}
async function load(){try{s=await api('/miniapp/mine');render()}catch(e){content.innerHTML='<section class="panel">'+e.message+'</section>'}}
async function reg(){try{s=await api('/miniapp/mine/register',{method:'POST'});render()}catch(e){alert(e.message)}}
async function dig(){if(busy)return;busy=true;try{const d=await api('/miniapp/mine/dig',{method:'POST'});s=d.state;render();note(d.message)}catch(e){alert(e.message);load()}finally{busy=false}}
async function startTicket(){if(busy)return;busy=true;try{const d=await api('/miniapp/gold-ticket/start',{method:'POST'});s=d.state;render();note('Золотой билет открыт. У тебя 3 попытки.')}catch(e){alert(e.message);load()}finally{busy=false}}
async function pickTicket(cell){if(busy)return;busy=true;try{const d=await api('/miniapp/gold-ticket/pick',{method:'POST',body:JSON.stringify({cell:cell})});s=d.state;render();note(d.prize?'Клетка принесла '+d.prize+' котоинов!':'В этой клетке ничего нет.')}catch(e){alert(e.message);load()}finally{busy=false}}
load();
</script>
</body></html>"""

