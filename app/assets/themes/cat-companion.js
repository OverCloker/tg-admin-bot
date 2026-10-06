import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {CatMotion} from './cat-motion.mjs';
import {solveCatLeg, modelXInBoneSpace,catSuspension,dampCatBody} from './cat-gait.mjs';

export async function createCatCompanion({canvas, host, reducedMotion, onError}) {
  const viewport = () => ({width: Math.min(innerWidth, window.visualViewport?.width || innerWidth),
    height: Math.min(innerHeight, window.visualViewport ? window.visualViewport.height + window.visualViewport.offsetTop : innerHeight)});
  const vp = viewport(), motion = new CatMotion(vp.width, vp.height, performance.now());
  let renderer;
  try { renderer = new THREE.WebGLRenderer({canvas, alpha: true, antialias: true, powerPreference: 'low-power'}); }
  catch (error) { throw new Error('На этом устройстве недоступен WebGL для 3D-котика.'); }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); renderer.setClearColor(0, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-.72, .72, .72, -.72, .01, 20);
  camera.position.set(0, .25, 3); camera.lookAt(0, .08, 0);
  camera.zoom = 1.3; camera.updateProjectionMatrix();
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb4afb5, 2.2));
  const light = new THREE.DirectionalLight(0xffffff, 2.4); light.position.set(2, 3, 4); scene.add(light);
  let gltf;
  try { gltf = await new GLTFLoader().loadAsync('/admin/theme-assets/owner-cat-v4.glb'); }
  catch (error) { renderer.dispose(); throw new Error('Не удалось загрузить модель котика. Попробуйте включить режим ещё раз.'); }
  const pivot = new THREE.Group();
  // Yaw first, then pitch in the cat's local forward plane (not screen X).
  pivot.rotation.order = 'YXZ'; pivot.add(gltf.scene); scene.add(pivot);
  const bones = new Map(); gltf.scene.traverse(o => { if (o.isBone) bones.set(o.name, o);
    if (o.isMesh) o.frustumCulled = false; });
  const rest = new Map([...bones].map(([name, b]) => [name, b.quaternion.clone()]));
  gltf.scene.updateMatrixWorld(true);
  const legChains = [['neck_02','extra_008','extra_009',0],['upperarm_r','lowerarm_r','hand_r',Math.PI],
    ['foot_r','ball_r','extra_018',Math.PI+.12],['extra_022','extra_023','extra_024',.12]];
  const hingeAxes = new Map(), legBind = new Map();
  const shoulderRest=new Map(),shoulderUp=new Map();
  for (const name of [...legChains.flatMap(chain=>chain.slice(0,3)),'spine_01','spine_02','extra_001']) {
    const bone = bones.get(name); if (!bone) continue;
    const bindWorld = bone.getWorldQuaternion(new THREE.Quaternion());
    hingeAxes.set(name,new THREE.Vector3(...modelXInBoneSpace(bindWorld.toArray())).normalize());
    const position=bone.getWorldPosition(new THREE.Vector3());legBind.set(name,[position.y,position.z]);
  }
  for(const [name] of legChains){
    const bone=bones.get(name);shoulderRest.set(name,bone.position.clone());
    shoulderUp.set(name,new THREE.Vector3(0,1,0).applyQuaternion(bone.parent.getWorldQuaternion(new THREE.Quaternion()).invert()));
  }
  const pelvis=bones.get('pelvis'), pelvisRest=pelvis?.position.clone();
  const pelvisDown=new THREE.Vector3(0,-.13,0), pelvisUp=new THREE.Vector3(0,1,0);
  if(pelvis)pelvisDown.applyQuaternion(pelvis.parent.getWorldQuaternion(new THREE.Quaternion()).invert());
  if(pelvis)pelvisUp.applyQuaternion(pelvis.parent.getWorldQuaternion(new THREE.Quaternion()).invert());
  const tailNames=['extra_011','extra_012','extra_013','extra_014','extra_015','extra_016','extra_017'];
  const tailDirection=new THREE.Vector3(),tailTarget=new THREE.Vector3(),tailDelta=new THREE.Quaternion(),tailWorld=new THREE.Quaternion(),parentWorld=new THREE.Quaternion();
  let enabled = false, frame = 0, lastRender = 0, disposed = false, sleepTimer = 0, contextLost = false;
  let yaw = 0, curl = 0, sit = 0, gait = 0, reach = 0, look = 0, lookPitch = 0, tuck = 0, compression = 0;
  let bodyHeight=0,bodyVelocity=0;
  const rotation = new THREE.Quaternion(), axis = new THREE.Vector3();
  const lerp = (value, target, dt, tau = .35) => value + (target - value) * (1 - Math.exp(-dt / tau));
  function turn(name, x = 0, y = 0, z = 0) {
    const bone = bones.get(name); if (!bone) return;
    if (x) bone.quaternion.multiply(rotation.setFromAxisAngle(hingeAxes.get(name) || axis.set(1, 0, 0), x));
    if (y) bone.quaternion.multiply(rotation.setFromAxisAngle(axis.set(0, 1, 0), y));
    if (z) bone.quaternion.multiply(rotation.setFromAxisAngle(axis.set(0, 0, 1), z));
  }
  function paint(s, dt) {
    const walking = !s.reduced && ['turning', 'settling', 'approaching', 'going-home'].includes(s.state);
    const reaching = s.state === 'reaching';
    const flying = s.state === 'leaping';
    const desiredCurl = s.state === 'curling' ? Math.min(1, s.age / 1800) : s.state === 'sleeping' ? 1 : 0;
    curl = lerp(curl, desiredCurl, dt, .55);
    gait = lerp(gait, walking ? Math.min(1,s.speed/.035) : 0, dt, .2);
    sit=lerp(sit,['sitting','curling','sleeping'].includes(s.state)?1:0,dt,.55);
    const paw = reaching ? Math.sin(Math.PI*Math.min(1,s.age/4200)) : 0;
    reach = lerp(reach, s.reduced ? 0 : paw, dt, .25);
    tuck = lerp(tuck, flying ? Math.sin(Math.PI * s.flight) : 0, dt, .1);
    const squash = s.state === 'crouching' ? Math.min(1,s.age/200) : s.state === 'landing' ? Math.sin(Math.PI*Math.min(1,s.age/360)) : 0;
    compression = lerp(compression,squash,dt,.08);
    // Moving feet turn the body; never spin it to a new idle viewing angle.
    const targetYaw = s.reduced ? s.facing*.35 : s.heading;
    let yawDelta = Math.atan2(Math.sin(targetYaw - yaw), Math.cos(targetYaw - yaw));
    yaw += yawDelta * (1 - Math.exp(-dt / .32));
    look = lerp(look, Math.max(-.3, Math.min(.3, (s.look.x - s.x - s.size / 2) / s.size)) * (1 - curl), dt, .3);
    lookPitch = lerp(lookPitch, Math.max(-.28, Math.min(.22, (s.look.y - s.y - s.size / 2) / s.size * .35)) * (1 - curl), dt, .3);
    for (const [name, bone] of bones) bone.quaternion.copy(rest.get(name));
    const suspension=dampCatBody(bodyHeight,bodyVelocity,catSuspension(s.phase,gait)*(1-sit),dt);
    bodyHeight=suspension.value;bodyVelocity=suspension.velocity;
    if(pelvis)pelvis.position.copy(pelvisRest).addScaledVector(pelvisDown,sit).addScaledVector(pelvisUp,bodyHeight);
    // A transferred rig cannot support the old deep fold without collapsing
    // the abdominal volume. Keep the lumbar bend shallow and the chest upright.
    const elastic=gait*(1-sit),backFlex=.022*elastic*Math.sin(s.phase),chestFlex=-.018*elastic*Math.sin(s.phase-.35);
    turn('spine_01',-.28*sit+backFlex);turn('spine_02',-.12*sit+chestFlex);
    for(const [name,,,phase] of legChains){
      const front=name==='neck_02'||name==='upperarm_r';
      // Scapulae glide with each foreleg; the spine is not a rigid chassis.
      bones.get(name).position.copy(shoulderRest.get(name)).addScaledVector(shoulderUp.get(name),
        (front?.005:.002)*elastic*Math.sin(s.phase+phase-.4));
    }
    pivot.updateMatrixWorld(true);
    const legPoint=name=>{const p=bones.get(name).getWorldPosition(new THREE.Vector3());pivot.worldToLocal(p);return [p.y,p.z];};
    for (const [hip, knee, wrist, phase] of legChains) {
      const front = hip === 'neck_02' || hip === 'upperarm_r';
      const planted=legBind.get(wrist);
      const step = solveCatLeg(legPoint(hip),legPoint(knee),legPoint(wrist),s.phase+phase,gait,[planted[0],planted[1]+(front?.032*gait*(1-sit):.045*sit)]);
      // Rest near the verified bind pose: large folds distort this transferred rig.
      turn(hip, step.hip + tuck * (front ? -.45 : .35) + compression * .18);
      // IK follows the actual joint chain, with the same model-space hinge plane.
      turn(knee, step.knee + tuck * (front ? .6 : -.6) - compression * .3);
      turn(wrist, step.wrist+step.toeRoll+(front?.4*sit:0));
    }
    // One small paw gesture, not a whole-body rotation pretending to rear up.
    turn('neck_02', -reach * .18); turn('extra_008', reach * .1);
    turn('spine_01', .01 * Math.sin(s.time * 2) * (1 - gait));
    turn('extra_001',sit*.15-(backFlex+chestFlex)*.65);
    turn('extra_003',sit*.25 + curl * .03 + lookPitch*(1-sit) + .025 * Math.sin(s.time)*(1-gait)
      -(backFlex+chestFlex)*.35+.012*elastic*Math.sin(s.phase-.7), look*(1-sit), .015 * Math.sin(s.time * .8));
    for (let i = 12; i <= 17; i++) turn(`extra_${String(i).padStart(3,'0')}`, 0,
      0, (1 - curl) * (.04 * Math.sin(s.time * 1.4 - (i - 12) * .25)
        +.025*elastic*Math.sin(s.phase-.8-(i-12)*.18)));
    // Keep gravity upright in every locomotion state: yaw only, never roll/pitch.
    pivot.rotation.set(0, yaw, 0, 'YXZ');
    pivot.position.set(0, -.08 - compression * .055, 0);
    // Guide the tail along a low wrap beside the haunches, without stretching bones.
    if(sit>.001){
      pivot.updateMatrixWorld(true);
      const base=bones.get(tailNames[0]).getWorldPosition(new THREE.Vector3());pivot.worldToLocal(base);
      const p1=new THREE.Vector3(-.2,-.28,-.28),p2=new THREE.Vector3(-.32,-.28,.2),p3=new THREE.Vector3(.02,-.28,.3);
      for(let i=0;i<tailNames.length-1;i++){
        const bone=bones.get(tailNames[i]),child=bones.get(tailNames[i+1]),t=i/(tailNames.length-1),q=1-t;
        tailTarget.copy(p1).sub(base).multiplyScalar(3*q*q).addScaledVector(new THREE.Vector3().copy(p2).sub(p1),6*q*t).addScaledVector(new THREE.Vector3().copy(p3).sub(p2),3*t*t).normalize().applyQuaternion(pivot.quaternion);
        tailDirection.copy(child.getWorldPosition(new THREE.Vector3())).sub(bone.getWorldPosition(new THREE.Vector3())).normalize();
        tailDelta.setFromUnitVectors(tailDirection,tailTarget);
        bone.getWorldQuaternion(tailWorld).premultiply(tailDelta);
        bone.parent.getWorldQuaternion(parentWorld).invert();tailWorld.premultiply(parentWorld);
        bone.quaternion.slerp(tailWorld,sit);bone.updateMatrixWorld(true);
      }
    }
    host.style.width = host.style.height = `${s.size}px`;
    host.style.transform = `translate3d(${s.x}px,${s.y}px,0)`;
    host.dataset.state = s.state; host.dataset.facing = s.facing < 0 ? 'left' : 'right';
    host.dataset.renderer = 'three'; host.dataset.visible = 'true'; canvas.dataset.pose = s.state;
    if (canvas.clientWidth !== s.size || canvas.width !== Math.round(s.size * renderer.getPixelRatio())) renderer.setSize(s.size, s.size, false);
    camera.position.y = .25; camera.lookAt(0, .08, 0);
    renderer.render(scene, camera);
  }
  function active() { return enabled && !document.hidden && !disposed && !contextLost; }
  function tick(now) {
    frame = 0; if (!active()) return;
    if (now - lastRender >= 1000 / 30) { const dt = Math.min(.064, (now - lastRender) / 1000 || .033);
      lastRender = now; paint(motion.step(now), dt); }
    if (!reducedMotion.matches) frame = requestAnimationFrame(tick);
  }
  function schedule() {
    clearTimeout(sleepTimer); sleepTimer = 0;
    if (active() && reducedMotion.matches) sleepTimer = setTimeout(() => {
      sleepTimer = 0; if (!active()) return; motion.home(performance.now()); paint(motion.step(performance.now()), 1);
    }, 18000);
  }
  function sync(value) {
    enabled = value; cancelAnimationFrame(frame); frame = 0; clearTimeout(sleepTimer); sleepTimer = 0;
    if (!active()) { motion.pause(performance.now()); host.dataset.visible = 'false'; return; }
    const p = viewport(); motion.resize(p.width, p.height); motion.reduced = reducedMotion.matches; motion.resume(performance.now());
    if (motion.reduced) { motion.move = null; motion.vx = motion.vy = 0; }
    paint(motion.step(performance.now()), 1); lastRender = performance.now();
    if (!motion.reduced) frame = requestAnimationFrame(tick); schedule();
  }
  function tap(x, y) { if (!active()) return; motion.tap(x, y, performance.now());
    if (motion.reduced) paint(motion.step(performance.now()), 1); schedule(); }
  function resize() { if (!active()) return; const p = viewport(); motion.resize(p.width, p.height);
    if (motion.reduced) paint(motion.step(performance.now()), 1); }
  function dispose() { enabled = false; sync(false); disposed = true;
    gltf.scene.traverse(o => { if (o.isMesh) { o.geometry.dispose();
      for (const material of (Array.isArray(o.material) ? o.material : [o.material])) {
        for (const v of Object.values(material)) if (v?.isTexture) v.dispose(); material.dispose(); } } }); renderer.dispose(); }
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); contextLost = true; sync(enabled);
    onError?.('Графика временно недоступна. Кот вернётся после восстановления.'); });
  canvas.addEventListener('webglcontextrestored', () => { contextLost = false; sync(enabled); onError?.(''); });
  return {sync, tap, resize, dispose};
}
