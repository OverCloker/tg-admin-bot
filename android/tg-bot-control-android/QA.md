# Abstergo 0.4.0 QA — 2026-10-08

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
