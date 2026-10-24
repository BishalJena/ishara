// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "SignPipeline",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "SignPipeline", targets: ["SignPipeline"]),
        .library(name: "SignPipelineMediaPipe", targets: ["SignPipelineMediaPipe"]),
    ],
    dependencies: [
        // MediaPipe's manifest uses unsafe linker flags, so SwiftPM only accepts it
        // pinned by revision, not by version. This is the MediaPipe Tasks iOS
        // 1.1.1 manifest commit.
        .package(
            url: "https://github.com/google-ai-edge/mediapipe",
            revision: "50505c8312c7eacb1bd411cecdc4cc9fd08d53cb"
        ),
    ],
    targets: [
        .target(name: "SignPipeline"),
        .target(
            name: "SignPipelineMediaPipe",
            dependencies: [
                "SignPipeline",
                // MediaPipe ships iOS device and simulator slices only.
                .product(
                    name: "MediaPipeTasksVision",
                    package: "mediapipe",
                    condition: .when(platforms: [.iOS])
                ),
            ]
        ),
        .testTarget(
            name: "SignPipelineTests",
            dependencies: ["SignPipeline"],
            resources: [.copy("Fixtures")]
        ),
        // Reads the gitignored TestAssets/ from the source tree, so it runs on
        // the iOS simulator (which shares the host file system) and skips when
        // Scripts/download_holistic_test_assets.sh has not been run.
        .testTarget(
            name: "SignPipelineMediaPipeTests",
            dependencies: ["SignPipelineMediaPipe", "SignPipeline"]
        ),
    ]
)
