#!/bin/bash

echo "Creating Xcode project for Ambient app..."

# Create a temporary Swift package to generate the project
cat > temp_package.swift << 'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AmbientTemp",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "AmbientTemp", targets: ["AmbientTemp"])
    ],
    targets: [
        .executableTarget(
            name: "AmbientTemp",
            path: "."
        )
    ]
)
EOF

# Use Xcode to create a new project
echo "Opening Xcode to create project..."
echo ""
echo "MANUAL STEPS REQUIRED:"
echo "1. Open Xcode"
echo "2. File > New > Project"
echo "3. Choose macOS > App"
echo "4. Product Name: Ambient"
echo "5. Organization Identifier: com.crestviewlabs"
echo "6. Interface: SwiftUI"
echo "7. Language: Swift"
echo "8. Save in the current macapp directory"
echo ""
echo "After creating the project:"
echo "1. Delete the default ContentView.swift"
echo "2. Add all files from the Ambient/ folder to the project"
echo "3. Add MetagenAPI package dependency:"
echo "   - File > Add Package Dependencies"
echo "   - Add Local > browse to ../api/swift"
echo ""
echo "Or alternatively, use the open command below to open an existing project:"

# Clean up
rm -f temp_package.swift

# If we had created a project successfully, we would open it
if [ -f "Ambient.xcodeproj/project.pbxproj" ]; then
    echo "Opening Ambient.xcodeproj..."
    open Ambient.xcodeproj
else
    echo ""
    echo "To manually create the project, run:"
    echo "  open /Applications/Xcode.app"
    echo ""
    echo "Or to open the experimental project as reference:"
    echo "  open ../../experimental/macapp/RecordingApp.xcodeproj"
fi