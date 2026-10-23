// swift-tools-version: 5.10

import PackageDescription

// Kept apart from SignPipeline so that package stays dependency-free and its tests
// run on macOS without cloning MediaPipe (~600 MB plus ~98 MB of binaries).
let package = Package(
    name: "SignPipelineMediaPipe",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "SignPipelineMediaPipe", targets: ["SignPipelineMediaPipe"]),
    ],
    dependencies: [
        .package(path: "../SignPipeline"),
        // MediaPipe's manifest uses unsafe linker flags, so SwiftPM only accepts it
        // pinned by revision, not by version. This is the MediaPipe Tasks iOS
        // 1.1.1 manifest commit.
        .package(
            url: "https://github.com/google-ai-edge/mediapipe",
            revision: "50505c8312c7eacb1bd411cecdc4cc9fd08d53cb"
        ),
    ],
    targets: [
        .target(
            name: "SignPipelineMediaPipe",
            dependencies: [
                .product(name: "SignPipeline", package: "SignPipeline"),
                // MediaPipe ships iOS device and simulator slices only.
                .product(
                    name: "MediaPipeTasksVision",
                    package: "mediapipe",
                    condition: .when(platforms: [.iOS])
                ),
            ]
        ),
    ]
)
