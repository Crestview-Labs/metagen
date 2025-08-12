// swift-tools-version:5.7
import PackageDescription

let package = Package(
    name: "MetagenAPI",
    platforms: [
        .macOS(.v12),
        .iOS(.v15)
    ],
    products: [
        .library(
            name: "MetagenAPI",
            targets: ["MetagenAPI"]
        )
    ],
    dependencies: [],
    targets: [
        .target(
            name: "MetagenAPI",
            dependencies: [],
            path: "Sources/MetagenAPI"
        ),
        .testTarget(
            name: "MetagenAPITests",
            dependencies: ["MetagenAPI"],
            path: "Tests/MetagenAPITests"
        )
    ]
)