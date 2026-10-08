# Abstergo Android 0.4.0

Native Android shell for https://app.otvet04ka.com/ with home-screen outage
widgets. Open **Адрес → Отключения света и виджет** to select a Poltava settlement
and the group for your house (1.1–6.2). Selection of a settlement does not infer
the house's group.

- **1×2**: next planned switch-on/off and its Kyiv time, including tomorrow when published.
- **4×2**: full-day timeline, current scheduled state, next boundary, last source update.

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

Release versionCode is 40000 (previous 0.3.4: 30004). Keep the existing signing
key for in-place upgrades. Publish explicitly with the repository's
`publish_android_release.py --caption-file android/tg-bot-control-android/release-caption.txt`.
