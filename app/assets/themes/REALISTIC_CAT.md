# Realistic Mini App cat

Asset: `realistic-cat-poses-v2.png`, 1254 × 1254 RGBA. Generated with the built-in
image generation tool, then copied into the project without pixel editing.
The controller samples 16 source cutouts and aligns their feet to one baseline;
these are not equal-height animation cells. Left-facing poses mirror the same cat.

Companion asset: `realistic-cat-gaze.png`, 1254 × 1254 RGBA, six seated gaze poses.
Both sheets are copied unchanged from built-in image generation. Source cutouts
are sampled in canvas; their feet share one baseline. Gaze body scale is .32;
action body scale is .61. The generator swapped the two upward looks, so the
source rectangle order explicitly maps them to left/right.

Behaviour: distant taps turn the seated cat's head without moving its torso.
Nearby taps trigger a horizontal walk along the bottom edge, then rising onto
hind paws, stretching and settling. No movement toward high buttons or random
jumps. Pose transitions blend over 180ms; standing time starts after walking
completes, and sleeping cats wake through crouched poses before reacting.
After 18 seconds without taps: move to a bottom corner, crouch, curl, sleep.
The next tap wakes the cat. Disabled mode loads no cat image; hidden documents
stop timers and drawing. Reduced-motion mode uses still poses and no frame loop.
The overlay cannot intercept input. No theme-specific layout or navigation changes.

Final image edit prompt (built-in tool, transparent background enabled):

> Edit target: supplied cat atlas. Keep the SAME realistic orange-white cat and all 16 poses. Correct ONLY the sprite atlas spacing and transparency: arrange EXACTLY four equally sized columns and four equally sized rows on a square transparent canvas. Every cat must fit entirely inside its own square tile, including tail, feet, ears and raised paws, with at least 8% transparent margin on all four sides. Reduce overall cat scale enough to fit the tallest standing pose. Preserve the same body scale across all frames, smaller idle/sleep silhouettes are expected. Align all paws/floor contact at 88% tile height. No overlap across cells, no stray red/yellow/white pixels or colored halos. Clean accurate alpha cutouts, only cat fur and whiskers visible. No text or guides or floor. Row1 sitting alert/blink/look up/turn; row2 rise/standing reach/fully reach/lower; row3 four walking-right cycle poses; row4 crouch/curl/sleep/sleep-breath. Critical exact uniform tile geometry, not a loose collage.

The generator did not produce uniform tile spacing, so production source rectangles
are explicitly declared in `catPoseRects`. Keep them in sync when replacing the atlas.

Checks: `node tests/test_cat_behavior.cjs` executes the production controller with a
controlled clock, including rapid taps, sleep/wake, viewport bounds, reduced motion,
capture-phase events and timer cleanup. `tests/test_miniapp_design.py` guards markup;
`tests/test_admin_access_keys.py` guards the public asset route.

Seated gaze generation prompt (built-in tool, transparent background enabled;
existing photographic atlas used as identity reference):

> Use case: photorealistic-natural. Reference image is cat identity and photographic fur style, NOT an edit target. Generate a NEW transparent animation sheet of the SAME lifelike orange tabby/white cat. EXACTLY six full-body seated poses arranged in 3 columns x 2 rows, generous transparent gutters, no overlap, no text. ALL SIX have the identical seated torso/paws/tail position facing directly forward, anchored feet at 86% of each cell, same scale and lighting. Change ONLY head/eyes between cells: top-left neutral looking forward; top-middle head gently turned looking LEFT horizontally; top-right head gently turned looking RIGHT horizontally; bottom-left head turned LEFT looking UP at a high button; bottom-middle head turned RIGHT looking UP at a high button; bottom-right same forward face eyes softly closed blink. Real feline anatomy, individual fur hairs and whiskers, natural amber eyes no cartoon proportions. Full cat inside each tile including tail. Soft neutral daylight, no floor no props, genuine alpha transparency. Body must remain seated and stationary between frames, only the neck/head turns. Clean production sprite sheet.
