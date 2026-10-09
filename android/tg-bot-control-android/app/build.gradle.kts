plugins {
    id("com.android.application")
}

android {
    namespace = "com.codex.tgbotcontrol"
    compileSdk = 35
    buildToolsVersion = "36.1.0"

    defaultConfig {
        applicationId = "com.codex.tgbotcontrol"
        minSdk = 26
        targetSdk = 35
        versionCode = 40005
        versionName = "0.4.5"
        manifestPlaceholders["widgetQaExported"] = providers.gradleProperty("widgetQa").orElse("false").get()
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {}
