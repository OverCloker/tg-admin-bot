/* Run with node tests/test_cat_behavior.cjs. Executes the production pet controller. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/miniapp_ui.py'), 'utf8');
const controller = source.split('  const playfulCat = ')[1].split('  enforceMiniAppTheme();')[0];
assert.ok(controller);
let now = 0, id = 0, saved = {cats:false}, plays = 0, pauses = 0, mirrors = 0;
const timers = new Map(), frames = new Map(), listeners = new Map();
const sprite = {dataset:{},style:{},getContext:() => ({
  clearRect(){},save(){},restore(){},translate(){},scale(x){if(x<0)mirrors++},drawImage(){}
})};
const pet = {dataset:{},style:{}};
const audio = {pause(){pauses++},play(){plays++; return Promise.resolve()}};
const document = {hidden:false, getElementById: id => ({playfulCat:pet,catSprite:sprite,catMeow:audio})[id],
  createElement:()=>({getContext:sprite.getContext}),
  addEventListener(name, callback, options){listeners.set(name, {callback,options})}};
const reducedMotion = {matches:false,addEventListener(){}};
const window = {innerWidth:390,innerHeight:844,addEventListener(){},
  visualViewport:{width:390,height:844,offsetTop:0,addEventListener(){}}};
class Element {
  constructor(rect, setting=false){this.rect=rect;this.setting=setting}
  closest(selector){return selector === '.cat-setting' ? (this.setting ? this : null) : this}
  getBoundingClientRect(){return this.rect}
}
const context = vm.createContext({document,window,reducedMotion,Element,
  performance:{now:()=>now},Image:class {constructor(){this.src='';this.complete=true;this.naturalWidth=1254;this.naturalHeight=836}},
  loadMiniSettings:()=>saved,saveMiniSettings:settings=>{saved=settings},
  setTimeout:(callback,delay)=>{timers.set(++id,{callback,at:now+delay});return id},
  clearTimeout:id=>timers.delete(id),
  requestAnimationFrame:callback=>{frames.set(++id,callback);return id},
  cancelAnimationFrame:id=>frames.delete(id)
});
vm.runInContext('const playfulCat = ' + controller, context);
const run = code => vm.runInContext(code, context);
const tick = time => {
  now=time;
  for (const [id,timer] of [...timers]) if (timer.at<=now) {timers.delete(id);timer.callback()}
  const callbacks=[...frames.values()]; frames.clear(); callbacks.forEach(callback=>callback(now));
};
const tap = (x,y,detail=1) => listeners.get('click').callback({detail,clientX:x,clientY:y,
  target:new Element({left:x-20,top:y-10,width:40,height:20})});

assert.equal(frames.size,0); assert.equal(timers.size,0); assert.equal(run('catAtlas.src'),'');
run('setCatMode(true)');
assert.equal(saved.cats,true); assert.equal(frames.size,1); assert.equal(timers.size,1);
assert.equal(listeners.get('click').options.capture,true);
const originalLeft=run('catLeft'), floor=run('catTop');
tap(20,220); assert.equal(pet.dataset.state,'watching'); assert.equal(run('catFacing'),-1);
tick(200);assert.equal(sprite.dataset.pose,'19');assert.equal(run('catLeft'),originalLeft);
tap(370,510); tick(360);assert.equal(sprite.dataset.pose,'20');assert.equal(run('catTop'),floor);
assert.equal(run('catLeft'),originalLeft); // Distant taps only turn the head.
tap(20,800);assert.equal(pet.dataset.state,'approaching');tick(720);
assert.ok(run('catLeft')<originalLeft); const intermediate=run('catLeft');
tap(370,800); // A new tap must continue from the actual current position, not teleport.
assert.equal(run('catMovement.fromLeft'),intermediate); assert.equal(run('catFacing'),1);
assert.equal(frames.size,1); assert.equal(timers.size,1); assert.equal(plays,4);
tick(2520); assert.equal(sprite.dataset.pose,'4');assert.equal(run('catTop'),floor);
window.visualViewport.width=375;run('resizeCatViewport()');
assert.equal(pet.dataset.state,'reaching');assert.equal(timers.size,1);
tick(3020);assert.equal(sprite.dataset.pose,'5');tick(3620);assert.equal(sprite.dataset.pose,'6');
tick(5520);assert.equal(pet.dataset.state,'watching');
tick(10600);assert.equal(pet.dataset.state,'idle');assert.equal(run('catTop'),floor);
tick(18720); assert.equal(pet.dataset.state,'going-home');
tick(20720); assert.equal(pet.dataset.state,'curling');
tick(21160); assert.equal(sprite.dataset.pose,'13');
tick(21921); assert.equal(pet.dataset.state,'sleeping'); assert.equal(sprite.dataset.pose,'14');
assert.ok(run('catTop')>=700);
tap(50,180); assert.equal(pet.dataset.state,'waking');tick(22621);
assert.equal(pet.dataset.state,'watching');assert.equal(sprite.dataset.pose,'19');
run('setCatMode(false)');
assert.equal(frames.size,0);assert.equal(timers.size,0);assert.equal(pet.dataset.visible,'false');
assert.ok(pauses>0);

// Narrow screen and a keyboard-reduced visual viewport never clip the pet.
window.innerWidth=320;window.visualViewport.width=320;window.visualViewport.height=300;
run('setCatMode(true)');tap(2000,2000);tick(now+1000);
assert.ok(run('catLeft')>=4 && run('catLeft')<=188);
assert.ok(run('catTop')>=4 && run('catTop')<=168);
window.visualViewport.height=844;run('resizeCatViewport()');tap(280,800);tick(now+300);
window.visualViewport.height=300;run('resizeCatViewport()');tick(now+100);
assert.ok(run('catTop')>=4 && run('catTop')<=168); // Resize during an unfinished move.
document.hidden=true;run('syncCatMode()');
assert.equal(frames.size,0);assert.equal(timers.size,0);assert.equal(pet.dataset.visible,'false');
document.hidden=false;reducedMotion.matches=true;run('syncCatMode()');
assert.equal(frames.size,0);tap(0,0,0);assert.equal(frames.size,0);
tick(now+18000);assert.equal(pet.dataset.state,'sleeping');assert.equal(sprite.dataset.pose,'14');
assert.equal(frames.size,0);
run('setCatMode(false)');
reducedMotion.matches=false;run('setCatMode(true)');
tap(20,280);tick(now+2000);assert.equal(pet.dataset.state,'reaching');
tick(now+1200);assert.equal(sprite.dataset.pose,'6');assert.equal(run('catFacing'),-1);
assert.ok(mirrors>0);assert.equal(run('catTop'),166);
run('setCatMode(false)');
console.log('Cat controller: grounded gaze left/right, horizontal walk, all standing poses, smooth interruptions, sleep/wake, resize, reduced motion, cleanup OK');
