import com.android.build.api.variant.HostTestBuilder
import org.gradle.api.tasks.util.PatternSet
import java.io.ByteArrayOutputStream
import java.util.Properties
import javax.inject.Inject

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// The Swift SDK for Android targets this API level; the app's minSdk must match it.
val minSdkVersion = 28
val swiftTriple = "aarch64-unknown-linux-android$minSdkVersion"

val localProperties = Properties().apply {
    rootProject.file("local.properties").takeIf { it.isFile }?.inputStream()?.use(::load)
}

fun toolchainSetting(property: String, environment: String, default: String): String =
    localProperties.getProperty(property) ?: providers.environmentVariable(environment).orNull ?: default

fun buildConfigString(value: String?): String =
    "\"" + value.orEmpty().trim().replace("\\", "\\\\").replace("\"", "\\\"") + "\""

val home: String = System.getProperty("user.home")
val swiftBinPath = toolchainSetting("swift.bin", "SWIFT_BIN", "$home/.swiftly/bin/swift")
val swiftSdk = toolchainSetting("swift.sdk", "SWIFT_SDK", "swift-6.4.2-RELEASE_android")
val ndkDirPath = toolchainSetting(
    "android.ndk", "ANDROID_NDK_HOME", "/opt/homebrew/share/android-commandlinetools/ndk/30.0.16248370",
)
val swiftRuntimeLibDir =
    "$home/Library/org.swift.swiftpm/swift-sdks/$swiftSdk.artifactbundle/swift-android/swift-resources/usr/lib/swift-aarch64/android"

android {
    namespace = "ai.ishara.demo"
    compileSdk = 36
    // The same NDK strips the Swift libraries; AGP needs its exact version alongside the path.
    ndkPath = ndkDirPath
    Properties().apply { File(ndkDirPath, "source.properties").takeIf { it.isFile }?.inputStream()?.use(::load) }
        .getProperty("Pkg.Revision")?.let { ndkVersion = it }

    defaultConfig {
        applicationId = "ai.ishara.demo"
        minSdk = minSdkVersion
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += "arm64-v8a" }
        // Untracked backend settings; empty when absent, and the app then can't place a live call.
        buildConfigField("String", "ISHARA_BACKEND_URL", buildConfigString(localProperties.getProperty("ishara.backendUrl")))
        buildConfigField("String", "ISHARA_APP_TOKEN", buildConfigString(localProperties.getProperty("ishara.appToken")))
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // Models are memory-mapped and clips read through file descriptors, so they must stay uncompressed.
    androidResources {
        noCompress += listOf("tflite", "task", "mp4", "mov", "m4v")
    }
}

/** Builds `libIsharaCore.so` with the Swift SDK for Android and collects it with every library it needs. */
abstract class BuildSwiftCore @Inject constructor(
    private val execOperations: ExecOperations,
    private val fileOperations: FileSystemOperations,
) : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sources: ConfigurableFileCollection

    @get:Internal
    abstract val packageDir: DirectoryProperty

    @get:Input
    abstract val configuration: Property<String>

    @get:Input
    abstract val triple: Property<String>

    @get:Input
    abstract val swiftBin: Property<String>

    @get:Input
    abstract val runtimeLibDir: Property<String>

    @get:Input
    abstract val ndkDir: Property<String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun build() {
        val swift = File(swiftBin.get())
        val ndk = File(ndkDir.get())
        val runtime = File(runtimeLibDir.get())
        if (!swift.canExecute()) {
            throw GradleException("Swift not found at $swift. Set swift.bin in android/local.properties or SWIFT_BIN.")
        }
        if (!ndk.isDirectory) {
            throw GradleException("Android NDK not found at $ndk. Set android.ndk in android/local.properties or ANDROID_NDK_HOME.")
        }
        if (!runtime.isDirectory) {
            throw GradleException("Swift SDK runtime not found at $runtime. Set swift.sdk in android/local.properties or SWIFT_SDK.")
        }
        val prebuilt = ndk.resolve("toolchains/llvm/prebuilt").listFiles().orEmpty()
        fun ndkFile(path: String) = prebuilt.map { it.resolve(path) }.firstOrNull { it.exists() }
            ?: throw GradleException("$path not found in the NDK at $ndk.")
        val readelf = ndkFile("bin/llvm-readelf")
        val libcxx = ndkFile("sysroot/usr/lib/aarch64-linux-android/libc++_shared.so")
        val systemLibs = ndkFile("sysroot/usr/lib/aarch64-linux-android/${triple.get().substringAfter("android")}")

        val swiftBuild = listOf(
            swift.path, "build", "--package-path", packageDir.get().asFile.path,
            "--swift-sdk", triple.get(), "-c", configuration.get(), "--product", "IsharaCore",
        )
        execOperations.exec {
            commandLine(swiftBuild)
            environment("ANDROID_NDK_HOME", ndk.path)
        }
        val binPath = ByteArrayOutputStream().also { output ->
            execOperations.exec {
                commandLine(swiftBuild + "--show-bin-path")
                environment("ANDROID_NDK_HOME", ndk.path)
                standardOutput = output
            }
        }.toString().trim()

        val available = (runtime.listFiles { file -> file.name.endsWith(".so") }.orEmpty().toList() + libcxx)
            .associateBy { it.name }
        val core = File(binPath, "libIsharaCore.so")
        val shipped = linkedMapOf(core.name to core)
        val pending = ArrayDeque(listOf(core))
        while (pending.isNotEmpty()) {
            val library = pending.removeFirst()
            for (needed in neededLibraries(readelf, library)) {
                if (systemLibs.resolve(needed).exists() || needed in shipped) continue
                val dependency = available[needed]
                    ?: throw GradleException("${library.name} needs $needed, which is neither an Android system library nor in the Swift SDK.")
                shipped[needed] = dependency
                pending.add(dependency)
            }
        }
        fileOperations.sync {
            from(shipped.values)
            into(outputDir.dir("arm64-v8a"))
        }
    }

    private fun neededLibraries(readelf: File, library: File): List<String> {
        val output = ByteArrayOutputStream()
        execOperations.exec {
            commandLine(readelf.path, "--dynamic", library.path)
            standardOutput = output
        }
        val needed = Regex("""\(NEEDED\)\s+Shared library: \[(.+)]""")
        return output.toString().lines().mapNotNull { needed.find(it)?.groupValues?.get(1) }
    }
}

/** Exposes the iOS app's recognition bundle (the single source) as an Android asset. */
abstract class CopyAslBundle @Inject constructor(
    private val fileOperations: FileSystemOperations,
) : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val bundle: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        fileOperations.sync {
            from(bundle)
            into(outputDir)
        }
    }
}

/** Copies whichever of the matching files exist under [sourceDir] (keeping their paths) into an asset folder. */
abstract class CopyOptionalAssets @Inject constructor(
    private val fileOperations: FileSystemOperations,
) : DefaultTask() {
    @get:Internal
    abstract val sourceDir: DirectoryProperty

    @get:Input
    abstract val patterns: ListProperty<String>

    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    val files: FileTree
        get() = sourceDir.asFileTree.matching(PatternSet().include(patterns.get()))

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        fileOperations.sync {
            from(sourceDir) { include(patterns.get()) }
            into(outputDir)
        }
    }
}

val swiftPackageDir = rootProject.layout.projectDirectory.dir("swift")
val iosPackagesDir = rootProject.layout.projectDirectory.dir("../ios/Packages")

val buildSwiftCore = listOf("debug", "release").associateWith { configuration ->
    tasks.register<BuildSwiftCore>("buildSwiftCore${configuration.replaceFirstChar(Char::uppercase)}") {
        group = "build"
        description = "Builds libIsharaCore.so ($configuration) with the Swift SDK for Android."
        sources.from(fileTree(swiftPackageDir) { include("Package.swift", "Package.resolved", "Sources/**") })
        for (dependency in listOf("CallSession", "RecognitionCore")) {
            sources.from(fileTree(iosPackagesDir.dir(dependency)) { include("Package.swift", "Sources/**") })
        }
        packageDir.set(swiftPackageDir)
        this.configuration.set(configuration)
        triple.set(swiftTriple)
        swiftBin.set(swiftBinPath)
        runtimeLibDir.set(swiftRuntimeLibDir)
        ndkDir.set(ndkDirPath)
        outputDir.set(layout.buildDirectory.dir("swift/$configuration/jniLibs"))
    }
}

val copyAslBundle = tasks.register<CopyAslBundle>("copyAslBundle") {
    bundle.set(rootProject.layout.projectDirectory.file("../ios/Ishara/Resources/asl-bundle.json"))
    outputDir.set(layout.buildDirectory.dir("generated/aslBundle/assets"))
}

// Recognition models (and, in debug builds, saved sign clips for the emulator) come from the iOS
// app's untracked LocalAssets folder, the single source; see ios/Ishara/LocalAssets/README.md.
val iosLocalAssets = rootProject.layout.projectDirectory.dir("../ios/Ishara/LocalAssets")
val recognitionModels = listOf("holistic_landmarker.task", "asl-signs.tflite")
val copyLocalAssets = listOf("debug", "release").associateWith { configuration ->
    tasks.register<CopyOptionalAssets>("copyLocalAssets${configuration.replaceFirstChar(Char::uppercase)}") {
        sourceDir.set(iosLocalAssets)
        patterns.set(if (configuration == "debug") recognitionModels + listOf("mp4", "mov", "m4v").map { "SampleSigns/*.$it" } else recognitionModels)
        outputDir.set(layout.buildDirectory.dir("generated/localAssets/$configuration"))
    }
}

// Instrumented tests read the iOS packages' own fixtures (single source): the detector fixtures and
// logits bundle (RecognitionCore), the LiteRT runtime parity logits, and MediaPipe's Holistic test
// photo (SignPipelineMediaPipe/TestAssets, from download_holistic_test_assets.sh; absent → tests skip).
val copyRecognitionTestFixtures = tasks.register<CopyOptionalAssets>("copyRecognitionTestFixtures") {
    sourceDir.set(iosPackagesDir)
    patterns.set(
        listOf(
            "RecognitionCore/Tests/RecognitionCoreTests/Fixtures/**/*.json",
            "SignPipelineLiteRT/Tests/SignPipelineLiteRTTests/Fixtures/*.json",
            "SignPipelineMediaPipe/TestAssets/*.jpg",
        ),
    )
    outputDir.set(layout.buildDirectory.dir("generated/recognitionTestFixtures"))
}

androidComponents {
    onVariants { variant ->
        val configuration = if (variant.buildType == "release") "release" else "debug"
        variant.sources.jniLibs?.addGeneratedSourceDirectory(buildSwiftCore.getValue(configuration), BuildSwiftCore::outputDir)
        variant.sources.assets?.addGeneratedSourceDirectory(copyAslBundle, CopyAslBundle::outputDir)
        variant.sources.assets?.addGeneratedSourceDirectory(copyLocalAssets.getValue(configuration), CopyOptionalAssets::outputDir)
        variant.androidTest?.sources?.assets
            ?.addGeneratedSourceDirectory(copyRecognitionTestFixtures, CopyOptionalAssets::outputDir)
        // Scripted landmarks and test doubles used by both the JVM and the device tests.
        variant.androidTest?.sources?.kotlin?.addStaticSourceDirectory("src/sharedTest/kotlin")
        variant.hostTests[HostTestBuilder.UNIT_TEST_TYPE]?.sources?.let { sources ->
            sources.kotlin?.addStaticSourceDirectory("src/sharedTest/kotlin")
            // JVM tests read SignPipeline's landmark fixture as a classpath resource.
            sources.resources?.addStaticSourceDirectory(
                iosPackagesDir.dir("SignPipeline/Tests/SignPipelineTests/Fixtures").asFile.path,
            )
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
    implementation(libs.mediapipe.tasks.vision)
    implementation(libs.litert)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)
    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)

    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.okhttp.mockwebserver3)
}
