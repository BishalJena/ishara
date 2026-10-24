// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "RecognitionCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "RecognitionCore", targets: ["RecognitionCore"]),
    ],
    targets: [
        .target(name: "RecognitionCore"),
        .testTarget(
            name: "RecognitionCoreTests",
            dependencies: ["RecognitionCore"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
