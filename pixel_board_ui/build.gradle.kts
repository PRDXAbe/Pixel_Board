import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    kotlin("jvm") version "2.0.21"
    kotlin("plugin.serialization") version "2.0.21"
    id("org.jetbrains.compose") version "1.7.1"
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21"
}

group = "com.pixelboard"
version = "1.0.0"

repositories {
    mavenCentral()
    google()
    maven("https://maven.pkg.jetbrains.space/public/p/compose/dev")
}

dependencies {
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation(compose.materialIconsExtended)

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    testImplementation(kotlin("test"))
}

compose.desktop {
    application {
        mainClass = "MainKt"

        // Pass the project root so the app can find ros_bridge.py and setup.bash
        jvmArgs += listOf("-DprojectRoot=${rootDir.parentFile.absolutePath}")

        nativeDistributions {
            targetFormats(TargetFormat.Deb)
            packageName = "pixel-board-ui"
            packageVersion = "1.0.0"
            description  = "Magic Board — LIDAR Smart Board UI"
        }
    }
}
