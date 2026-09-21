plugins {
    id("com.android.application")
}
android {
    namespace = "jp.xiaqui.marketweather"
    compileSdk = 35
    defaultConfig {
        applicationId = "jp.xiaqui.marketweather"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    buildTypes { release { isMinifyEnabled = false } }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
tasks.register<Copy>("renameDebugApk") {
    dependsOn("assembleDebug")
    from(layout.buildDirectory.file("outputs/apk/debug/app-debug.apk"))
    into(layout.buildDirectory.dir("outputs/apk/market-weather"))
    rename { "market-weather-debug.apk" }
}
