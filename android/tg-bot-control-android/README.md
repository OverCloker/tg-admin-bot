# Abstergo Android 0.4.6

Release workflow (user instruction, 2026-10-09): after verifying a requested
Abstergo update, publish the finished APK to the staff Releases topic with the
changelog automatically, without asking for another publication confirmation.
Use the existing publisher and destination; do not publish incomplete builds.

OEM resize compatibility: launchers without OPTION_APPWIDGET_SIZES use their
actual min/max dimensions and separate orientation views, never hard-coded
miniature fallbacks. Native rounded backgrounds retain a fixed dp corner radius
through resizing. Force Dark is disabled for explicitly colored widget views:
Light remains light in device dark mode; OLED/System selection still works.

The power page uses the selected schedule-first design: editable address summary,
current schedule status, Today/Tomorrow controls, readable semantic interval rows,
and a separate widget section with native appearance preview. All adaptive widget
layouts share its green/coral surfaces, round energy icon and typography.
Location text alone is not a confirmed selection; choose a search result and group.

Appearance settings: Light, Dark OLED (#000000) or Device theme; background
transparency 0–100%. Text/icons and interval panels remain readable and opaque.
Apply separately per widget. App settings without a widget set new-widget defaults.
Device theme refreshes on running process configuration changes or next refresh.

Native Android shell for https://app.otvet04ka.com/ with home-screen outage
widgets. Open **Адрес → Отключения света и виджет** to select any settlement
in the site's catalog and the group for your house. Groups are loaded for the
selected location (including Kyiv's extended groups). Selection of a settlement does not infer
the house's group.

- **One adaptive widget**: resize horizontally and vertically using the launcher's handles.
  Small sizes show the next event; medium sizes add context; wide sizes add a timeline;
  tall sizes show fixed-height intervals. Large schedules show current/upcoming rows
  and a link to the full day instead of shrinking text or overflowing the widget.
- Available minimum size depends on the launcher; 1×1 uses a minimal time/status view.
- A whole day with light uses a dedicated summary, never one giant stretched row.
- Preview support: packaged PNG fallback, Android 12 layout and Android 15 generated preview.
  Old compact/list providers are retained for existing widgets but excluded from home-screen selection.

Each widget has separate preferences. Tap its body to configure; tap ↻ to
refresh. Cached dated schedules remain available offline. Missing/unknown
schedules are not shown as electricity available. Android can delay background
updates (15-minute jobs, schedule-boundary jobs and 30-minute widget callbacks).
Actual emergency outages may differ from the published schedule.

Source: https://bezsvitla.com.ua/ via `/power/locations` and `/power/schedule`
in the admin API. Deploy the API before distributing the APK.

Build this directory with JDK 17, Gradle 8.9, Android SDK platform 35 and build
tools 36.1.0: `gradle :app:assembleDebug`. Output:
`app/build/outputs/apk/debug/app-debug.apk`.

An unpublished dated schedule is shown as «Сегодня без графиков»; connection
failures and not-yet-loaded schedules are separate states.

Release versionCode is 40006 (0.4.5: 40005; previous 0.3.4: 30004). Keep the existing signing
key for in-place upgrades. Publish explicitly with the repository's
`publish_android_release.py --caption-file android/tg-bot-control-android/release-caption.txt`.

For local native design QA only, build with `-PwidgetQa=true` to export the debug
snapshot Activity. Distributed builds omit this flag; the QA Activity is not exported.
See `design-qa.md` for reference comparison and known physical-launcher test gaps.
