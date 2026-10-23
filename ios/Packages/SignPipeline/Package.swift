// swift-tools-version: 5.10

import PackageDescription

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
