// swift-tools-version: 5.10

import PackageDescription

// No dependencies on purpose: the MediaPipe adapter lives in ../SignPipelineMediaPipe,
// so this package builds and tests on macOS without cloning MediaPipe.
let package = Package(
    name: "SignPipeline",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "SignPipeline", targets: ["SignPipeline"]),
    ],
    targets: [
        .target(name: "SignPipeline"),
        .testTarget(
            name: "SignPipelineTests",
            dependencies: ["SignPipeline"],
            resources: [.copy("Resources")]
        ),
    ]
)
