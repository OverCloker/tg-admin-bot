# Mini App 3D cat

Production serves the checked-in bundle and GLB from the same-origin asset allowlist.
No Node runtime or CDN is needed on the server. To rebuild after editing the JS:

    npm install
    npm run build

Use `node tests/test_cat_behavior.cjs` from the repository root for deterministic
movement tests. `cat-motion.mjs` handles trajectories and inactivity;
`cat-companion.js` handles WebGL, anatomical bone mappings, and smooth pose blending.

`owner-cat-v3.glb` is a simplified copy of the user's `result (1).glb`, with a
locally transferred 43-joint rig from the user's `model (1).glb`. Source files were
not changed. The shipped mesh has 57,471 triangles / 37,951 vertices (~4.85 MB).
The three embedded test clips are retained; the interactive runtime uses procedural
poses. This is a prototype transferred rig, not a professionally authored cat rig.
The v4 derivative stores its JPEG texture as a separate same-origin asset so the
Mini App's strict Content Security Policy can load it without creating a blob URL.
Strong bends, especially fur around the shoulders and tail, still need visual QA.
Whole-model roll/pitch and simulated rearing are deliberately disabled: the model
stays upright during locomotion. A proper rear-leg-supported standing pose remains
future rig/animation work, not a rotation of the complete mesh.
Arrival now includes a stepping turn to face the viewer, then a separate sitting
pose with planted forefeet and a low tail wrap. A real lying-down or curled sleeping
clip still needs authoring and validation. The internal sleep state currently
reuses the seated pose, not a real sleeping clip.

Three.js license is retained in `app/assets/themes/THREE-LICENSE.txt` and the bundle.
Cat mode is opt-in, skips pointer interception, loads lazily, pauses in background,
and renders static poses instead of RAF motion when reduced motion is requested.

Locomotion now uses the real upper/lower leg chains (the donor's rear clavicle-like
helper bones are not animated as hips). Planar two-bone IK calculates lift and a
52% contact phase in a diagonal-pair light trot; foot angles counter the knee/hip motion. Stance no longer adds
a permanent 8 mm paw lift or lowers the entire root during walking. A critically
damped, stride-driven pelvis suspension is applied before IK so support feet
compensate for body height. Swing clearance is 42 mm; nominal stride is 120 mm
(up from 80 mm). Cadence now uses actual orthographic model-to-pixel scale and
contact duration: at 180 px overlay width a full cycle spans 37.5 px of travel,
not the previous arbitrary 45 px. Horizontal reach eases into each leg's physical limit
without stretching bones or lifting grounded paws. This is not a flight-phase gallop.
Step amplitude ramps with travel speed. Forefeet are placed closer below the
shoulders, allowing the wide step without straight-knee clipping. Small scapular
glides and lumbar/thoracic flexion are applied before IK; head counter-motion and
delayed tail motion soften the rigid chassis silhouette. Swing includes wrist/toe
flexion rather than carrying a permanently flat paw. Hind contact has a small
delay relative to the diagonally paired forefoot, not perfect robotic synchrony.
Direction changes use a short walking Bezier arc and tangent-following heading,
not a stationary spin. This is still procedural planar locomotion, not full 3D
foot-contact IK on a scene floor or a motion-captured cat walk.

`owner-cat-v4.glb` is the active derivative. It repairs central lower torso weights,
which incorrectly carried ~56% aggregate limb influence. Smooth anatomical masks
and pelvis/spine interpolation reduce that influence to ~3.6% in the audited
region. v3 and the user's source meshes remain unchanged. Natural gait quality is
still unfinished; deterministic tests validate geometry/math, not lifelike motion.
The sitting pose now uses a shallower lumbar bend and 130 mm pelvis descent,
instead of the deep 200 mm fold that visibly collapsed the belly. Forefeet keep
their original ground height; hind feet draw forward under the haunches. A proper
volume-preserving rig/pose corrective remains necessary for larger folds.
