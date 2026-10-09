# Abstergo 0.4.0 QA — 2026-10-08

## 0.4.5 native redesign — 2026-10-09

Build and upgrade passed on Pixel 6/API35. Live city search/selection,
group selection 60.1, schedule load, Today/Tomorrow and OLED persistence tested
using UI-tree coordinates. Eight RemoteViews snapshots and the selected mock
were visually compared; see design-qa.md. Original default light theme restored.

## 0.4.4 appearance QA — 2026-10-09

Android 15 emulator: build passed; selected widget retained appearance settings
after reopening, other widgets retained their preferences. Snapshot background
RGBA: light (255,252,247,255), OLED (0,0,0,255), 50% (0,0,0,128),
100% (0,0,0,0). System-theme snapshots switched with emulator night mode.
Night mode restored; crash buffer empty. Live launcher configuration callback
was not independently confirmed for the selected instance. OEM testing remains.

Environment: Pixel 6 Android 15/API 35 emulator, Pixel Launcher, existing local
debug signing key. Built with JDK 17 / Gradle 8.9 / AGP 8.7.3.

Verified:

- Installed original user-supplied 0.3.4 APK, then upgraded in place to 0.4.0.
  Package versionCode increased from 30004 to 40000; panel URL remained saved.
- Searched Чутове via native UI against the live-source isolated API, selected
  a returned settlement and group; today's intervals loaded.
- Added both widgets using Android's pin-widget dialog. Launcher reported 1×2
  and 4×2; screenshots showed complete state/time and the 24-hour timeline.
- Changed only compact widget to 3.2; large widget remained 3.1. Opened their
  separate configuration screens, including with an existing Activity task.
- Loaded groups 3.1 and 3.2 via the deployed public API and the native Activity.
- Tomorrow's unpublished schedule produced an explicit no-schedule message.
- Disabled Wi-Fi and mobile data only in the emulator, forced the update job:
  both retained current-day schedules and marked them as saved data. Restored
  both network interfaces afterward.
- The 3.1 state changed to scheduled electricity available at the 18:00 Kyiv
  boundary while using cached data, with the next boundary shown as 21:00.
- Crash buffer remained empty. Five parser/validation unit tests passed.

Not asserted: actual electricity at a house, emergency outages, exact background
execution timing under OEM battery restrictions, or layouts on every launcher.
Android may delay jobs. Only Poltava settlements are supported in this release.

## 0.4.2 widget verification (2026-10-09)

- Android 15 pin dialogs show distinct previews and sizes 2×1, 2×4 and 4×2.
- Added compact 2×1 and interval-list 2×4 on the launcher using saved Kyiv 60.1.
- Inspected screenshots: list highlights the current interval, dims past rows,
  and uses green light / red outage icons. Corrected stretched bitmap proportions.
- Crash buffer was empty. Existing widgets retain their configurations.
- Existing 1×2 launcher allocations must be removed and added again as 2×1.
- Not verified on third-party launchers or Android versions older than 12
  (previewLayout is supported from Android 12).

## 0.4.1 verification (2026-10-09)

- Installed 0.4.1 over 0.4.0 on the Android 15 emulator.
- Verified native Kryvyi Rih search and unpublished-schedule display in both
  pinned widget sizes: “Сегодня без графиков”, with a neutral timeline.
- Verified Kyiv group 60.1 restoration and loading its published intervals.
- Live read-only probes covered Kyiv, Kryvyi Rih, Chutove and Cherkasy.
- 61 automated tests passed, including outage parsing, access checks and
  mocked unmute operations. No live chat member was unmuted during testing.
- Admin panel JavaScript syntax check passed.
- All regions advertised by the source are now accepted. An absent schedule
  is distinct from a connection failure; neither proves actual power availability.
