# Android source recovery

Recovered on 2026-10-08 from the local archive `Codex-updated-2026-09-25.rar`,
member `Codex/2026-06-04/new-chat/outputs/tg-bot-control-android`.

The archive declared version 0.2.2 (versionCode 5). Later shell changes were
reconstructed against the user's installed `Abstergo-0.3.4.apk` using JADX 1.5.6:
public URL default/migration, theme system-bar colors, Android 13 back callback,
web-panel back handling and double-back exit confirmation. New version 0.4.0
uses versionCode 40000, above 0.3.4's 30004. The previous APK signing certificate
matches the local debug key; in-place upgrade was verified on Android 15.

Native Android sources were removed during workspace cleanup when their dated
parent directory was mistaken for an obsolete project. Build outputs, IDE caches,
and machine-specific `local.properties` were not restored. The recovered source
now resides inside the active bot repository to avoid that ambiguity.
