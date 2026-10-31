// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "IsharaAndroidBridge",
    products: [
        .library(name: "IsharaCore", type: .dynamic, targets: ["IsharaCore"]),
    ],
    dependencies: [
        .package(path: "../../ios/Packages/CallSession"),
        .package(path: "../../ios/Packages/RecognitionCore"),
    ],
    targets: [
        .target(
            name: "CAndroidBridge",
            linkerSettings: [.linkedLibrary("android"), .linkedLibrary("log")]
        ),
        .target(
            name: "IsharaCore",
            dependencies: [
                "CAndroidBridge",
                .product(name: "CallSession", package: "CallSession"),
                .product(name: "RecognitionCore", package: "RecognitionCore"),
            ]
        ),
    ]
)
