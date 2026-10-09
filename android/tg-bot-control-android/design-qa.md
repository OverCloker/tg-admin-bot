# Power page and widgets — selected direction 2, Abstergo 0.4.5

final result: passed

## Current visual evidence

- Selected source: design-evidence/selected-power-page.png, 853×1844.
  User selected the second displayed concept; source was refined to three
  themes and the actual Без Світла source before implementation.
- Implementation: design-evidence/power-page-native.png, native full-content
  capture at 1080px width/density 2.625. The screen is Android, not a web clone.
- Content comparison: power-comparison.png; readable top-region comparison:
  power-focus.png. Normalize both to 390px width without stretching.
  Source is 390×843 after scaling. Implementation content is 390×1052
  after removing reserved system-bar padding. Actual viewport is 411dp wide.
- Matched state: Київ, 2.2, 2026-10-09 12:31, identical five sample intervals.
  View.draw captures full native content; live screenshots and UI-tree tests
  independently checked the scrollable screen and controls.
- Widgets: widget-045-matrix.png shows 180/260dp × 80/180/300/420dp
  for the requested eight sizes. Physical cell sizes are launcher-dependent.

## Fix / recapture history

1. [P2] Small appearance preview broke the word «Отключение».
   Shorten the event label at narrow widths, reduce event time to 22sp.
   The latest page comparison shows readable «Откл.» and time.
2. [P2] 2×2 footer was clipped after adding schedule-qualified detail text.
   Use a one-line compact detail and compact layout under 170dp at narrow widths.
   Revised widget-045-180x180.png shows the complete source/time and refresh icon.
3. Comparison-only capture issue: transparent view pixels became black when
   converted to RGB. Fill the native capture canvas with the actual page surface,
   then recapture; the live screen itself was never black.

## Required fidelity surfaces

- Typography: native Roboto/sans-serif with medium heading/active weights,
  12–15sp body, 19sp hero and 30sp title. Hierarchy matches the target.
- Spacing: address summary, hero, dates, rows, refresh, then settings. Native
  44–48dp touch targets and the retained explicit Apply button create a longer,
  scrollable page than the static concept. This is an intentional native adaptation,
  not an attempt to squeeze readable settings into the reference's fixed height.
- Colors: #FFFCF7, #1B2232, #176B43, #EDF5EE, #AF4334, #FCEEE9;
  OLED preserves #000000 and opaque readable foregrounds.
- Assets: official Tabler map-pin, pencil, filled bolt, existing bulb/refresh
  library icons; no raster decorations in the source. Native widget preview,
  not a fake bitmap screenshot used as an interactive UI.
- Copy: actual source, schedule-qualified state, no false availability when
  unpublished. Theme modes corrected to Light/OLED/System. Small preview
  emphasizes next event; bigger widgets add current state/day intervals.

## Interactions / gaps

- Real UI tested: open address editor, autocomplete for Київ, select returned
  city, scroll/select group 60.1, save and load actual source data.
- Today/Tomorrow switching: tomorrow without a published schedule correctly
  displays «Завтра без графиков». Today restores dated data.
- OLED Apply persisted after reopening; light mode restored afterward.
- Fresh Android crash buffer empty. Eight widget snapshots rendered.
- Per-widget caches and settings retained; no server/chat mutations.
- Physical OEM launcher, extreme font scaling and all Android releases remain
  device-test gaps. Native 12sp dates are abbreviated rather than full prose.
- P3: source's subtle gradient omitted for stable semantic fills; native library
  line icons replace tiny decorative dots. No actionable P0/P1/P2 findings remain.

## Earlier widget baseline (0.4.3)

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
- Additional size matrix: 2×1, 2×2, 2×3, 2×4, 3×1, 3×2, 3×3, 3×4.
  Representative widths 180/260dp and heights 80/180/300/420dp were applied
  with the same data; no clipped content or crash was observed.
  Evidence: design-evidence/size-matrix.png. Actual cell-to-dp mapping is
  determined by the user's launcher, not by these representative QA sizes.
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
