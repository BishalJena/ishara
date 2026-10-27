// swift-tools-version: 5.10

import PackageDescription

// Kept apart from SignPipeline so that package stays dependency-free. Google ships the iOS
// LiteRT runtime as a CocoaPod only (Swift Package Manager support is "in progress"), so the
// pod's prebuilt C library is used directly as a binary target: run
// Scripts/download_tflite_c.sh once before opening the app project. Its symbols do not overlap
// MediaPipe's own embedded copy of TensorFlow Lite (checked with nm on 27 Oct 2026).
let package = Package(
    name: "SignPipelineLiteRT",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "SignPipelineLiteRT", targets: ["SignPipelineLiteRT"]),
    ],
    dependencies: [
        .package(path: "../SignPipeline"),
    ],
    targets: [
        .binaryTarget(name: "TensorFlowLiteC", path: "Frameworks/TensorFlowLiteC.xcframework"),
        .target(
            name: "SignPipelineLiteRT",
            dependencies: [
                .product(name: "SignPipeline", package: "SignPipeline"),
                // The xcframework has iOS device and simulator slices only.
                .target(name: "TensorFlowLiteC", condition: .when(platforms: [.iOS])),
            ],
            linkerSettings: [.linkedLibrary("c++")]
        ),
        // Loads ios/Ishara/LocalAssets/asl-signs.tflite from the source tree, so it runs on the
        // iOS simulator (which shares the host file system) and skips without the model.
        .testTarget(
            name: "SignPipelineLiteRTTests",
            dependencies: [
                "SignPipelineLiteRT",
                .product(name: "SignPipeline", package: "SignPipeline"),
            ],
            resources: [.copy("Fixtures")]
        ),
    ]
)
