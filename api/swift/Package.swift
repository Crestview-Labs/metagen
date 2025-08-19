// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MetagenAPI",
    platforms: [
        .macOS(.v13),
        .iOS(.v16)
    ],
    products: [
        .library(
            name: "MetagenAPI",
            targets: ["MetagenAPI"]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-openapi-generator", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", from: "1.0.0"),
    ],
    targets: [
        .target(
            name: "MetagenAPI",
            dependencies: [
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
                .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
            ],
            path: "Sources/MetagenAPI",
            plugins: [
                .plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")
            ]
        ),
        .testTarget(
            name: "MetagenAPITests",
            dependencies: ["MetagenAPI"],
            path: "Tests/MetagenAPITests"
        )
    ]
)