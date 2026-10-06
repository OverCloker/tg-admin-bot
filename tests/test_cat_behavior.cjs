/* Deterministic checks against production locomotion, not a test-only imitation. */
const assert = require('node:assert/strict');
(async()=>{
 const {CatMotion}=await import('../app/assets/themes/cat-motion.mjs');
 const {modelXInBoneSpace,solveCatLeg,catSuspension,dampCatBody,catPhaseAdvance,CAT_STRIDE,CAT_CONTACT,CAT_VIEW_SPAN}=await import('../app/assets/themes/cat-gait.mjs');
 const pixelsPerCycle=180*(CAT_STRIDE/CAT_CONTACT)/CAT_VIEW_SPAN;
 assert.ok(Math.abs(catPhaseAdvance(pixelsPerCycle,180)-Math.PI*2)<1e-10);
 const contactTravel=180*CAT_STRIDE/CAT_VIEW_SPAN;
 assert.ok(Math.abs(catPhaseAdvance(contactTravel,180)-CAT_CONTACT*Math.PI*2)<1e-10,
   'screen travel during contact must match projected paw travel');
 const hinge=modelXInBoneSpace([0,0,Math.SQRT1_2,Math.SQRT1_2]);
 assert.ok(Math.abs(hinge[0])<1e-10&&Math.abs(hinge[1]+1)<1e-10&&hinge[2]===0);
 assert.deepEqual(modelXInBoneSpace([0,0,0,1]),[1,0,0]);
 const hip=[.04,.318],knee=[-.063,.271],foot=[-.221,.275];
 const planted=[foot[0],foot[1]+.032];
 const contactA=solveCatLeg(hip,knee,foot,.15*Math.PI*2,1,planted);
 const contactB=solveCatLeg(hip,knee,foot,.35*Math.PI*2,1,planted);
 const bodyTravel=CAT_STRIDE/CAT_CONTACT*(.35-.15);
 assert.ok(Math.abs(contactB.target[1]-contactA.target[1]+bodyTravel)<1e-8,
   'planted paw should remain still while the body advances through stance');
 const midStance=solveCatLeg(hip,knee,foot,.26*Math.PI*2,1);
 assert.ok(Math.abs(midStance.hip)<1e-8&&Math.abs(midStance.knee)<1e-8,
   'mid-stance must retain normal leg extension, not impose a crouch');
 for(const phase of [0,.6,3,4.8,6.2]){
   const step=solveCatLeg(hip,knee,foot,phase,1);
   const rotate=(v,a)=>[v[0]*Math.cos(a)-v[1]*Math.sin(a),v[0]*Math.sin(a)+v[1]*Math.cos(a)];
   const upper=rotate([knee[0]-hip[0],knee[1]-hip[1]],step.hip);
   const lower=rotate([foot[0]-knee[0],foot[1]-knee[1]],step.hip+step.knee);
   assert.ok(Math.abs(hip[0]+upper[0]+lower[0]-step.target[0])<1e-6);
   assert.ok(Math.abs(hip[1]+upper[1]+lower[1]-step.target[1])<1e-6);
   assert.ok(Math.abs(step.hip+step.knee+step.wrist)<1e-8);
 }
 for(const phase of [0,1,2,3]){
   const step=solveCatLeg(hip,knee,foot,phase,1);
   assert.equal(step.lift,0,'stance must not permanently lift the paws');
   assert.ok(Math.abs(step.target[0]-foot[0])<1e-8,'wide stance must keep the floor height');
   assert.ok(catSuspension(phase,1)>=0&&catSuspension(phase,1)<=.003);
 }
 let spring={value:0,velocity:0};
 for(let i=0;i<120;i++){
   spring=dampCatBody(spring.value,spring.velocity,.003,1/30);
   assert.ok(spring.value>=0&&spring.value<=.003,'suspension must not overshoot');
 }
 assert.ok(Math.abs(spring.value-.003)<1e-7);
 assert.ok(solveCatLeg(hip,knee,foot,0,1).offset>.04,'trot stride is wider than walk');
 for(const boundary of [0,.52*Math.PI*2,Math.PI*2]){
   const before=solveCatLeg(hip,knee,foot,boundary-1e-6,1);
   const after=solveCatLeg(hip,knee,foot,boundary+1e-6,1);
   assert.ok(Math.abs(before.hip-after.hip)<1e-4&&Math.abs(before.knee-after.knee)<1e-4);
 }
 const cat=new CatMotion(400,800);
 let now=0;const seen=new Set();
 function advance(ms){const end=now+ms;while(now<end){now=Math.min(now+16,end);
   const beforeY=cat.y,beforeState=cat.state;const s=cat.step(now);seen.add(s.state);
   assert.ok(s.x>=4&&s.x<=cat.maxX&&s.y>=4&&s.y<=cat.maxY);
   if(beforeState==='approaching'&&s.state==='approaching')assert.equal(cat.y,beforeY);
 }}
 cat.tap(50,100,now);assert.equal(cat.state,'turning');assert.equal(cat.facing,-1);
 advance(500);assert.equal(cat.state,'turning');assert.ok(cat.y<616);assert.ok(cat.phase>0);
 assert.ok(Number.isFinite(cat.heading)&&cat.heading!==0);
 while(cat.state!=='leaping'&&now<5000)advance(16);
 assert.equal(cat.state,'leaping');
 assert.ok(seen.has('approaching'));assert.ok(seen.has('crouching'));assert.ok(seen.has('leaping'));
 // While airborne, new input queues instead of steering the cat like a dragged sticker.
 if(cat.state==='leaping'){
   const originalGoal={...cat.goal},pos={x:cat.x,y:cat.y};
   cat.tap(350,300,now);cat.tap(320,200,now);
   assert.deepEqual(cat.goal,originalGoal);assert.deepEqual(cat.pending,{x:320,y:200});
   assert.equal(cat.x,pos.x);assert.equal(cat.y,pos.y);
 }
 advance(10000);
 for(const state of ['landing','settling','sitting'])assert.ok(seen.has(state),state);
 assert.equal(cat.pending,null);
 assert.equal(cat.heading,0);assert.equal(cat.state,'sitting');
 advance(26000);assert.equal(cat.state,'sleeping');assert.equal(cat.y,cat.maxY);
 cat.tap(60,60,now);assert.equal(cat.state,'waking');
 cat.tap(320,200,now+100);assert.deepEqual(cat.pending,{x:320,y:200});
 advance(1000);assert.notEqual(cat.state,'waking');
 const paused={x:cat.x,y:cat.y};cat.pause(now);cat.step(now+90000);
 assert.equal(cat.x,paused.x);assert.equal(cat.y,paused.y);
 now+=90000;cat.resume(now);cat.step(now);assert.equal(cat.x,paused.x);assert.equal(cat.y,paused.y);
 cat.resize(90,120);advance(15000);
 const reduced=new CatMotion(400,800);reduced.reduced=true;
 reduced.tap(5,10,1);assert.equal(reduced.move,null);assert.equal(reduced.state,'watching');
 reduced.step(19000);assert.equal(reduced.state,'sleeping');assert.equal(reduced.y,reduced.maxY);
 const rapid=new CatMotion(390,844);
 for(let t=0;t<6000;t+=16){const p={x:rapid.x,y:rapid.y};
  if(t%64===0){rapid.tap(t%390,t%844,t);assert.equal(rapid.x,p.x);assert.equal(rapid.y,p.y);}
  const s=rapid.step(t);assert.ok(Number.isFinite(s.x+s.y));
  assert.ok(s.x>=4&&s.x<=rapid.maxX&&s.y>=4&&s.y<=rapid.maxY);
 }
 console.log('Cat locomotion: all checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
