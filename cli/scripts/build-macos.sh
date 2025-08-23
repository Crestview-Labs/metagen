#!/bin/bash
# Build script for macOS distribution of Ambient CLI

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Ambient CLI - macOS Build Script${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLI_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
PROJECT_ROOT="$( cd "$CLI_DIR/.." && pwd )"

# Configuration
BUILD_DIR="$CLI_DIR/build"
DIST_DIR="$CLI_DIR/dist-macos"
BUNDLE_NAME="ambient-macos"

echo -e "${GRAY}CLI Directory: $CLI_DIR${NC}"
echo -e "${GRAY}Project Root: $PROJECT_ROOT${NC}"
echo ""

# Step 1: Clean previous builds
echo -e "${BLUE}📦 Cleaning previous builds...${NC}"
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

# Step 2: Build TypeScript
echo -e "${BLUE}📦 Building TypeScript...${NC}"
cd "$CLI_DIR"
npm run build

# Step 3: Copy Python backend
echo -e "${BLUE}📦 Copying Python backend...${NC}"
mkdir -p "$BUILD_DIR/backend"

# Copy essential Python files
cp "$PROJECT_ROOT/main.py" "$BUILD_DIR/backend/"
cp "$PROJECT_ROOT/pyproject.toml" "$BUILD_DIR/backend/"

# Copy Python source directories
for dir in metagen tests; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        cp -r "$PROJECT_ROOT/$dir" "$BUILD_DIR/backend/"
    fi
done

# No additional config files needed - pyproject.toml already copied

# Step 4: Copy built JavaScript and node_modules
echo -e "${BLUE}📦 Copying built JavaScript and dependencies...${NC}"
cp -r "$CLI_DIR/dist" "$BUILD_DIR/"
cp -r "$CLI_DIR/node_modules" "$BUILD_DIR/"
cp "$CLI_DIR/package.json" "$BUILD_DIR/"

# Step 5: Create wrapper script
echo -e "${BLUE}📦 Creating wrapper script...${NC}"
cat > "$BUILD_DIR/ambient" << 'EOF'
#!/bin/bash
# Ambient CLI wrapper script

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set up environment
export AMBIENT_HOME="$HOME/.ambient"
export AMBIENT_BACKEND_DIR="$SCRIPT_DIR/backend"
export METAGEN_PROJECT_ROOT="$SCRIPT_DIR/backend"

# Run the Node.js CLI
exec node "$SCRIPT_DIR/dist/cli/src/index.js" "$@"
EOF

chmod +x "$BUILD_DIR/ambient"

# Step 6: Bundle with pkg (optional - for standalone executable)
if command -v pkg &> /dev/null; then
    echo -e "${BLUE}📦 Creating standalone executable with pkg...${NC}"
    
    # Create package.json for pkg
    cat > "$BUILD_DIR/package.json" << EOF
{
  "name": "ambient-cli",
  "version": "1.0.0",
  "main": "dist/index.js",
  "bin": "dist/index.js",
  "pkg": {
    "targets": ["node18-macos-arm64", "node18-macos-x64"],
    "outputPath": "$DIST_DIR",
    "assets": [
      "backend/**/*"
    ]
  }
}
EOF
    
    # Copy node_modules and dist
    cp -r "$CLI_DIR/node_modules" "$BUILD_DIR/"
    cp -r "$CLI_DIR/dist" "$BUILD_DIR/"
    
    # Run pkg
    cd "$BUILD_DIR"
    npx pkg . --targets node18-macos-arm64,node18-macos-x64 --output "$DIST_DIR/ambient"
    
    echo -e "${GREEN}✓ Standalone executable created${NC}"
else
    echo -e "${GRAY}pkg not found, skipping standalone executable creation${NC}"
fi

# Step 6: Create tarball distribution
echo -e "${BLUE}📦 Creating tarball distribution...${NC}"
cd "$BUILD_DIR"
tar -czf "$DIST_DIR/$BUNDLE_NAME.tar.gz" .

# Step 7: Create install script
echo -e "${BLUE}📦 Creating install script...${NC}"
cat > "$DIST_DIR/install.sh" << 'EOF'
#!/bin/bash
# Ambient CLI installer for macOS

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m'

echo -e "${BLUE}🚀 Ambient CLI Installer${NC}"
echo ""

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js is required but not installed.${NC}"
    echo "Please install Node.js 18+ from https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}❌ Node.js 18+ is required (found v$NODE_VERSION).${NC}"
    exit 1
fi

# Installation directory
INSTALL_DIR="/usr/local/ambient"
BIN_LINK="/usr/local/bin/ambient"

echo -e "${GRAY}Installation directory: $INSTALL_DIR${NC}"
echo -e "${GRAY}Binary link: $BIN_LINK${NC}"
echo ""

# Request sudo if needed
if [ ! -w "/usr/local" ]; then
    echo "Administrator privileges required for installation."
    sudo -v
fi

# Extract tarball
echo -e "${BLUE}📦 Extracting files...${NC}"
TEMP_DIR=$(mktemp -d)
tar -xzf ambient-macos.tar.gz -C "$TEMP_DIR"

# Install files
echo -e "${BLUE}📦 Installing Ambient CLI...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${GRAY}Removing previous installation...${NC}"
    sudo rm -rf "$INSTALL_DIR"
fi

sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$TEMP_DIR"/* "$INSTALL_DIR/"

# Create symlink
echo -e "${BLUE}📦 Creating command link...${NC}"
sudo rm -f "$BIN_LINK"
sudo ln -s "$INSTALL_DIR/ambient" "$BIN_LINK"

# Clean up
rm -rf "$TEMP_DIR"

echo ""
echo -e "${GREEN}✅ Ambient CLI installed successfully!${NC}"
echo ""
echo "Next steps:"
echo "  1. Run 'ambient setup' to initialize the environment"
echo "  2. Run 'ambient' to start the CLI"
echo ""
echo "For help, run: ambient --help"
EOF

chmod +x "$DIST_DIR/install.sh"

# Step 8: Create README
echo -e "${BLUE}📦 Creating README...${NC}"
cat > "$DIST_DIR/README.md" << 'EOF'
# Ambient CLI for macOS

## Installation

### Quick Install

```bash
./install.sh
```

### Manual Install

1. Extract the tarball:
   ```bash
   tar -xzf ambient-macos.tar.gz
   ```

2. Copy to installation directory:
   ```bash
   sudo cp -r ambient /usr/local/
   sudo ln -s /usr/local/ambient/ambient /usr/local/bin/ambient
   ```

## First Time Setup

After installation, run the setup command to initialize your environment:

```bash
ambient setup
```

This will:
- Download the uv Python package manager (if needed)
- Create a Python 3.11 virtual environment
- Install all required Python dependencies

## Usage

Start the interactive chat interface:
```bash
ambient
```

Or send a single message:
```bash
ambient -m "Your message here"
```

### Available Commands

- `ambient` - Start interactive chat (default)
- `ambient setup` - Initialize/update environment
- `ambient server start` - Start backend server
- `ambient server stop` - Stop backend server
- `ambient server status` - Check server status
- `ambient status` - Check overall system status
- `ambient --help` - Show help

## Requirements

- macOS 10.15 or later
- Node.js 18 or later
- Internet connection (for initial setup)

## Troubleshooting

If you encounter issues:

1. Check Node.js version:
   ```bash
   node --version  # Should be 18+
   ```

2. Re-run setup:
   ```bash
   ambient setup --force
   ```

3. Check logs:
   ```bash
   tail -f ~/.ambient/profiles/default/logs/backend.log
   ```

## Uninstall

To remove Ambient CLI:

```bash
sudo rm -rf /usr/local/ambient
sudo rm /usr/local/bin/ambient
rm -rf ~/.ambient
```
EOF

# Step 9: Summary
echo ""
echo -e "${GREEN}✅ Build complete!${NC}"
echo ""
echo -e "Distribution files created in: ${BLUE}$DIST_DIR${NC}"
echo ""
echo "Contents:"
ls -lh "$DIST_DIR"
echo ""
echo "To test the build locally:"
echo "  1. cd $DIST_DIR"
echo "  2. ./install.sh"
echo "  3. ambient setup"
echo "  4. ambient"