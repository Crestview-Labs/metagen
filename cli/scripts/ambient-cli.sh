#!/bin/bash
# Simple local test script for Ambient CLI

set -e

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

# Get the CLI directory (where this script lives)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLI_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo -e "${BLUE}🚀 Testing Ambient CLI locally${NC}"

# Change to CLI directory
cd "$CLI_DIR"

# Build TypeScript
echo -e "${BLUE}Building TypeScript...${NC}"
npm run build

# Set environment variables
export METAGEN_PROJECT_ROOT="$( cd "$CLI_DIR/.." && pwd )"
export AMBIENT_HOME="$HOME/.ambient"

# Run the CLI directly
echo -e "${GREEN}✓ Build complete. Starting CLI...${NC}"
echo ""
exec node "$CLI_DIR/dist/cli/src/index.js" "$@"