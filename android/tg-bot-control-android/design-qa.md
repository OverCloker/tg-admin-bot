# Adaptive outage widget — selected direction 1

final result: passed

## Visual truth and evidence

- Source: design-evidence/selected-design.png (1254×1254).
- Same-input comparison: design-evidence/comparison.png (1024×1180).
- Native implementation: design-evidence/tall.png (472×1103), wide.png
  (840×394), all-day.png (472×1103).
- Target native viewports: 180×420dp, 320×150dp; Android 15 emulator,
  density 2.625. No CSS viewport: these are native Android RemoteViews.
- State: Чутове, group 2.2, 2026-10-09, 14:45 Kyiv; identical sample intervals.
- Source tall widget crop (616,143)–(1204,1106) is uniformly scaled to width
  472px; native evidence is not stretched. The source concept's aspect ratio is
  not a literal Android cell allocation. Native height follows the launcher.
- Full-view and focused row/icon/type comparison are together in comparison.png.

## Comparison history

1. [P1] Bitmap rows expanded to fill height, making a single interval enormous.
   Replaced them with native fixed-height rows and a separate all-day summary.
2. [P1] Wide widget's timeline/footer were below the allocated height.
   Added a horizontal wide composition; native 320×150dp now fits both.
3. [P2] Narrow headers/status broke words and hid the footer.
   Added a dedicated narrow layout and row limits; 110×280dp was recaptured,
   with readable title/status/interval and visible footer.
4. [P2] Initial outage icon was unlike the chosen outlined bulb.
   Imported Tabler bulb/bulb-off source geometry; final comparison contains
   the revised library icons.
5. Native apply test rejected setSelected as unsupported in RemoteViews.
   Removed it; current-row emphasis now uses a supported styled text and
   background resource. Fresh crash buffer remained empty afterward.

## Required fidelity surfaces

- Typography: native sans/Roboto, clear bold event/time hierarchy; normal
  12–16sp UI and 26–36sp event time. Minimal 1×1/narrow views deliberately
  simplify content rather than fitting a full table into one cell.
- Spacing: warm rounded surface, purposeful header/status grouping,
  fixed 40dp rows with 5dp gaps; no stretched text or giant row.
  Footer remains anchored, with full day accessible through body click.
- Colors: ink #1B2232, warm surface #FFFCF7, soft green #EDF6EE and
  coral #FCECE7; current row uses a semantic border. Past text is muted.
- Assets: official Tabler/Material vectors, no emoji or hand-drawn icons.
  Preview PNG comes from actual native rendering, has transparency,
  uses drawable-nodpi, and is explicitly marked as an example.
- Copy: schedule-based wording, Kyiv time, actual source Без Світла.
  No invented outages in unpublished/no-data states. All-day-light state
  is separate from “Сегодня без графиков”. Current tall status and next
  event remain distinct.

## Interaction evidence

- Installed over existing version in the emulator.
- Native pin dialog displayed the actual preview and one adaptive provider.
- Added it to the launcher; resized that SAME widget from 4×2 to 2×2 and
  2×1 using UI-tree-derived resize-handle coordinates. Group 60.1 remained.
- Body opens configuration; existing pin/configuration flows remain.
- Applied/rendered compact, card, wide, tall, 1×1, narrow, all-day and
  unpublished cases in the native QA harness.
- Preview layers: PNG fallback, Android 12 layout, Android 15 generated
  preview. QA export is disabled by default in the distributed build.

## Accepted adaptations and test gaps

- Native cell allocations are not the mock's presentation-board proportions.
  Text labels beside row icons are omitted at narrow widths; accessible row
  descriptions retain status. Native highlight uses a border, not a stripe.
- No actionably clipped content remains in the tested normal-density cases.
- The user's physical OEM launcher has not been tested. It may cache old
  previews or constrain cell sizes differently. Font scaling, other OEM
  launchers and Android <12 are not exhaustively validated.
- P3: subtle mock shadow is intentionally omitted; launcher owns widget
  background/masking and elevation. Emergency outages are not guaranteed.
