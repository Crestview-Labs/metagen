#!/bin/bash

set -e

echo "🏗️  Building Ambient Mac App"
echo "============================"

# Check if Xcode is installed
if ! command -v xcodebuild &> /dev/null; then
    echo "❌ Xcode is required to build the Mac app"
    echo "   Please install Xcode from the Mac App Store"
    exit 1
fi

# Check if XcodeGen is installed
if ! command -v xcodegen &> /dev/null; then
    echo "⚠️  XcodeGen not found. Installing via Homebrew..."
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew is required to install XcodeGen"
        echo "   Install Homebrew from https://brew.sh"
        exit 1
    fi
    
    # Install XcodeGen
    brew install xcodegen
    
    if ! command -v xcodegen &> /dev/null; then
        echo "❌ Failed to install XcodeGen"
        exit 1
    fi
    echo "✅ XcodeGen installed successfully"
fi

# Check if we need to regenerate Xcode project
NEEDS_REGEN=0
if [ ! -d "Ambient.xcodeproj" ]; then
    NEEDS_REGEN=1
    echo "🔧 Xcode project not found, will generate..."
else
    # Check if any source files are newer than the project
    for swift_file in $(find Ambient -name "*.swift" -newer Ambient.xcodeproj 2>/dev/null); do
        echo "🔍 Detected new/modified file: $(basename $swift_file)"
        NEEDS_REGEN=1
        break
    done
    
    # Check if project.yml is newer
    if [ "project.yml" -nt "Ambient.xcodeproj" ]; then
        echo "🔍 project.yml has been modified"
        NEEDS_REGEN=1
    fi
fi

if [ $NEEDS_REGEN -eq 1 ]; then
    echo "🔧 Regenerating Xcode project..."
    xcodegen generate --spec project.yml --project Ambient.xcodeproj
    
    if [ ! -d "Ambient.xcodeproj" ]; then
        echo "❌ Failed to generate Xcode project"
        exit 1
    fi
    echo "✅ Xcode project regenerated"
else
    echo "✅ Xcode project is up to date"
fi

# Build the Swift API package first
echo "📦 Building MetagenAPI package..."
cd ../api/swift
swift build

# Return to macapp directory
cd ../../macapp

# Build the Mac app
echo "🔨 Building Mac app..."
xcodebuild -scheme Ambient -configuration Release -derivedDataPath build -skipPackagePluginValidation

# Find the built app
APP_PATH="build/Build/Products/Release/Ambient.app"

if [ -d "$APP_PATH" ]; then
    echo "✅ Build successful!"
    echo "📍 App location: $APP_PATH"
    
    # Optionally copy to Applications
    read -p "Copy to /Applications? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp -r "$APP_PATH" /Applications/
        echo "✅ Copied to /Applications"
    fi
else
    echo "❌ Build failed - app not found at expected location"
    exit 1
fi