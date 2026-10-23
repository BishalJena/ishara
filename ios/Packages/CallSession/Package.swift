// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "CallSession",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "CallSession", targets: ["CallSession"]),
    ],
    targets: [
        .target(name: "CallSession"),
        .testTarget(name: "CallSessionTests", dependencies: ["CallSession"]),
    ]
)
