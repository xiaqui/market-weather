plugins {
    id("com.android.application")
}

val ciKeystorePath = providers.environmentVariable("MW_KEYSTORE_FILE").orNull
val ciKeystorePassword = providers.environmentVariable("MW_KEYSTORE_PASSWORD").orNull
val ciKeyAlias = providers.environmentVariable("MW_KEY_ALIAS").orNull
val ciKeyPassword = providers.environmentVariable("MW_KEY_PASSWORD").orNull
val hasCiSigning = listOf(
    ciKeystorePath,
    ciKeystorePassword,
    ciKeyAlias,
    ciKeyPassword,
).all { !it.isNullOrBlank() }

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

    if (hasCiSigning) {
        signingConfigs {
            create("ciFixed") {
                storeFile = file(ciKeystorePath!!)
                storePassword = ciKeystorePassword
                keyAlias = ciKeyAlias
                keyPassword = ciKeyPassword
            }
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfigs.findByName("ciFixed")?.let {
                signingConfig = it
            }
        }
        getByName("release") {
            isMinifyEnabled = false
        }
    }

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
