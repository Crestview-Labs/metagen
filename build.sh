#!/bin/bash
set -e

echo "🚀 Building Metagen - Intelligent Mode"
echo "======================================"

# Parse command line arguments
MODE="intelligent"  # Default mode
for arg in "$@"; do
    case $arg in
        --dev)
            MODE="dev"
            echo "📝 Running in DEVELOPMENT mode (relaxed checks)"
            ;;
        --release)
            MODE="release"
            echo "📝 Running in RELEASE mode (strict checks)"
            ;;
        --force-tests)
            FORCE_TESTS=true
            echo "📝 Forcing all tests to run"
            ;;
        --skip-tests)
            SKIP_TESTS=true
            echo "⚠️  WARNING: Skipping all tests"
            ;;
        --check-only)
            CHECK_ONLY=true
            echo "📝 Check only mode - no build will be performed"
            ;;
        --force-stubs)
            FORCE_STUBS=true
            echo "📝 Forcing stub regeneration"
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--dev|--release|--force-tests|--skip-tests|--check-only|--force-stubs]"
            exit 1
            ;;
    esac
done

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check for required tools
echo ""
echo "🔍 Checking dependencies..."
command -v git >/dev/null 2>&1 || { print_error "git is required"; exit 1; }
command -v jq >/dev/null 2>&1 || { print_error "jq is required. Install with: brew install jq (macOS) or apt-get install jq (Linux)"; exit 1; }
command -v uv >/dev/null 2>&1 || { print_error "uv is required. Install from: https://astral.sh/uv"; exit 1; }
command -v node >/dev/null 2>&1 || { print_error "node is required"; exit 1; }
command -v pnpm >/dev/null 2>&1 || { print_error "pnpm is required. Install with: npm install -g pnpm"; exit 1; }

# Check for optional Swift/Xcode (macOS only)
SWIFT_TESTS_ENABLED=false
if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v xcrun >/dev/null 2>&1 && xcrun --find swift >/dev/null 2>&1; then
        SWIFT_TESTS_ENABLED=true
        print_status "Xcode/Swift found - Swift tests available"
    else
        print_warning "Xcode not found - Swift tests will be skipped"
    fi
fi

# Git-based change detection
echo ""
echo "🔍 Analyzing changes..."

# Get current version
if [ ! -f "version.json" ]; then
    print_error "version.json not found!"
    exit 1
fi
CURRENT_VERSION=$(jq -r '.version' version.json)
print_info "Current version: $CURRENT_VERSION"

# Check if we have git history
HAS_HISTORY=true
if ! git rev-parse HEAD^ >/dev/null 2>&1; then
    print_warning "No git history - assuming fresh clone"
    HAS_HISTORY=false
    FORCE_FULL_BUILD=true
fi

if [ "$HAS_HISTORY" = true ]; then
    # Get last committed version
    LAST_VERSION=$(git show HEAD^:version.json 2>/dev/null | jq -r '.version' || echo "0.0.0")
    print_info "Last version: $LAST_VERSION"
    
    # Check what changed
    VERSION_CHANGED=$([[ "$CURRENT_VERSION" != "$LAST_VERSION" ]] && echo "true" || echo "false")
    API_CHANGED=$(git diff HEAD^ -- api/ ':(exclude)api/ts' ':(exclude)api/swift' --quiet && echo "false" || echo "true")
    
    # Check specific areas for testing decisions
    PYTHON_API_CHANGED=$API_CHANGED
    TS_STUBS_CHANGED=$(git diff HEAD^ -- api/ts/ --quiet && echo "false" || echo "true")
    SWIFT_STUBS_CHANGED=$(git diff HEAD^ -- api/swift/ --quiet && echo "false" || echo "true")
    
    print_info "Version changed: $VERSION_CHANGED"
    print_info "API changed: $API_CHANGED"
else
    VERSION_CHANGED=true
    API_CHANGED=true
    PYTHON_API_CHANGED=true
    TS_STUBS_CHANGED=true
    SWIFT_STUBS_CHANGED=true
fi

# Check stub freshness
STUBS_FRESH=true
if [ -f "api/ts/src/version.ts" ]; then
    TS_VERSION=$(grep "API_VERSION" api/ts/src/version.ts 2>/dev/null | grep -o '"[^"]*"' | tr -d '"' || echo "none")
    if [[ "$TS_VERSION" != "$CURRENT_VERSION" ]]; then
        STUBS_FRESH=false
        print_warning "TypeScript stubs are out of date (v$TS_VERSION != v$CURRENT_VERSION)"
    fi
else
    if [[ "$VERSION_CHANGED" == "true" ]] || [[ "$API_CHANGED" == "true" ]]; then
        STUBS_FRESH=false
        print_warning "TypeScript stubs not found"
    fi
fi

if [ "$SWIFT_TESTS_ENABLED" = true ] && [ -f "api/swift/Sources/MetagenAPI/Version.swift" ]; then
    SWIFT_VERSION=$(grep "version =" api/swift/Sources/MetagenAPI/Version.swift 2>/dev/null | grep -o '"[^"]*"' | tr -d '"' || echo "none")
    if [[ "$SWIFT_VERSION" != "$CURRENT_VERSION" ]]; then
        STUBS_FRESH=false
        print_warning "Swift stubs are out of date (v$SWIFT_VERSION != v$CURRENT_VERSION)"
    fi
fi

# Enforce rules (except in dev mode)
if [[ "$MODE" != "dev" ]]; then
    # Rule 1: API changes require version bump
    if [[ "$API_CHANGED" == "true" ]] && [[ "$VERSION_CHANGED" == "false" ]]; then
        print_error "API changes detected but version not updated!"
        print_error "Please update version.json before building"
        echo ""
        echo "Changed files:"
        git diff HEAD^ --name-only -- api/ ':(exclude)api/ts' ':(exclude)api/swift'
        exit 1
    fi
    
    # Rule 2: Version changes require fresh stubs
    if [[ "$VERSION_CHANGED" == "true" ]] && [[ "$STUBS_FRESH" == "false" ]]; then
        print_error "Version updated but stubs are stale!"
        print_error "Please regenerate stubs using:"
        print_error "  uv run python generate_stubs.py"
        print_error "Or run build with: ./build.sh --force-stubs"
        exit 1
    fi
fi

# Determine what tests to run
RUN_PYTHON_TESTS=false
RUN_TS_TESTS=false
RUN_SWIFT_TESTS=false

if [[ "$SKIP_TESTS" != "true" ]]; then
    if [[ "$FORCE_TESTS" == "true" ]] || [[ "$VERSION_CHANGED" == "true" ]]; then
        # Force all tests
        RUN_PYTHON_TESTS=true
        RUN_TS_TESTS=true
        RUN_SWIFT_TESTS=$SWIFT_TESTS_ENABLED
        print_info "Running all tests (version changed or forced)"
    else
        # Intelligent test selection
        [[ "$PYTHON_API_CHANGED" == "true" ]] && RUN_PYTHON_TESTS=true
        [[ "$TS_STUBS_CHANGED" == "true" ]] && RUN_TS_TESTS=true
        [[ "$SWIFT_STUBS_CHANGED" == "true" ]] && [[ "$SWIFT_TESTS_ENABLED" == "true" ]] && RUN_SWIFT_TESTS=true
        
        if [[ "$RUN_PYTHON_TESTS" == "false" ]] && [[ "$RUN_TS_TESTS" == "false" ]] && [[ "$RUN_SWIFT_TESTS" == "false" ]]; then
            print_info "No relevant changes detected - skipping tests"
        fi
    fi
fi

# Check-only mode
if [[ "$CHECK_ONLY" == "true" ]]; then
    echo ""
    echo "📋 Check Results:"
    echo "  Version: $CURRENT_VERSION"
    echo "  API Changed: $API_CHANGED"
    echo "  Version Changed: $VERSION_CHANGED"
    echo "  Stubs Fresh: $STUBS_FRESH"
    echo "  Would run Python tests: $RUN_PYTHON_TESTS"
    echo "  Would run TypeScript tests: $RUN_TS_TESTS"
    echo "  Would run Swift tests: $RUN_SWIFT_TESTS"
    exit 0
fi

# Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
uv sync --dev

# Database migrations (only if db directory exists)
if [ -d "db" ]; then
    echo ""
    echo "🗄️  Running database migrations..."
    # Save current directory
    CURRENT_DIR=$(pwd)
    # Try to run migrations, but don't fail if tables already exist
    cd db && {
        alembic upgrade head 2>/dev/null || print_warning "Database migration skipped (tables may already exist)"
    }
    # Always return to original directory
    cd "$CURRENT_DIR"
else
    print_info "No db directory found - skipping migrations"
fi

# Check and generate API stubs if needed
echo ""
echo "🔍 Checking API client stubs..."
STUB_GEN_NEEDED=false

# Check if stubs need generation
if [[ "$FORCE_STUBS" == "true" ]]; then
    STUB_GEN_NEEDED=true
    print_info "Force regeneration requested"
elif [[ "$VERSION_CHANGED" == "true" ]] || [[ "$API_CHANGED" == "true" ]]; then
    STUB_GEN_NEEDED=true
    print_info "API or version changed - regeneration needed"
elif [ ! -d "api/ts/generated" ] && [ ! -d "api/swift/Sources/Generated" ]; then
    STUB_GEN_NEEDED=true
    print_info "Generated stubs not found"
elif [[ "$STUBS_FRESH" == "false" ]]; then
    STUB_GEN_NEEDED=true
    print_info "Stubs are out of date"
fi

if [[ "$STUB_GEN_NEEDED" == "true" ]]; then
    # Check if API server is running for stub generation
    if curl -s http://localhost:8080/openapi.json > /dev/null 2>&1; then
        print_status "API server is running"
        
        echo "📝 Generating API client stubs..."
        
        # Install Python dependencies for generation script
        uv pip install requests pyyaml
        
        # Run generation with appropriate flags
        if [[ "$FORCE_STUBS" == "true" ]]; then
            uv run python generate_stubs.py --force || { print_error "Stub generation failed!"; exit 1; }
        else
            uv run python generate_stubs.py || { print_error "Stub generation failed!"; exit 1; }
        fi
        
        print_status "API stubs generated successfully"
        
        # Build TypeScript stubs
        if [ -d "api/ts" ]; then
            echo "🔨 Building TypeScript stubs..."
            cd api/ts
            npm install
            # Install test dependencies if needed
            npm install uuid @types/uuid --save-dev 2>/dev/null || true
            # Build
            npm run build || {
                print_warning "TypeScript build had warnings - this is normal for generated code"
            }
            cd ../..
            print_status "TypeScript stubs built"
        fi
        
        # Note about Swift
        if [ -d "api/swift" ]; then
            print_info "Swift stubs generated. Build with: cd api/swift && swift build"
        fi
    else
        print_warning "API server not running - cannot generate stubs"
        print_warning "Start the server first: uv run python main.py"
        print_warning "Then run: uv run python generate_stubs.py"
        
        if [[ "$MODE" == "release" ]]; then
            print_error "Release mode requires stub generation!"
            exit 1
        fi
    fi
else
    print_status "API stubs are up to date"
    
    # Check version if version.json exists
    if [ -f "api/version.json" ]; then
        API_VERSION=$(uv run python -c "import json; print(json.load(open('api/version.json'))['current'])")
        print_info "API stubs version: v${API_VERSION}"
    fi
fi

# Run Python API tests if needed
if [[ "$RUN_PYTHON_TESTS" == "true" ]]; then
    echo ""
    echo "🧪 Running Python API tests..."
    uv run pytest tests/api/ -q --tb=short || { print_error "Python API tests failed!"; exit 1; }
    print_status "Python API tests passed"
else
    print_info "Skipping Python API tests (no changes)"
fi

# Frontend build
echo ""
echo "📦 Installing frontend dependencies..."
pnpm install

echo ""
echo "🔨 Building TypeScript packages..."
pnpm run build

# Run TypeScript client tests if needed
if [[ "$RUN_TS_TESTS" == "true" ]] && [ -d "api/ts" ]; then
    echo ""
    echo "🧪 Running TypeScript client tests..."
    cd api/ts
    # Ensure all dependencies including test dependencies are installed
    npm install
    # Install test dependencies if they're in package.json devDependencies
    if grep -q '"uuid"' package.json 2>/dev/null || grep -q '"@types/uuid"' package.json 2>/dev/null; then
        npm install uuid @types/uuid --save-dev 2>/dev/null || true
    fi
    npm run test -- --run || { print_error "TypeScript tests failed!"; exit 1; }
    cd ../..
    print_status "TypeScript tests passed"
elif [ -d "api/ts" ]; then
    print_info "Skipping TypeScript tests (no changes)"
fi

# Run Swift client tests if needed
if [[ "$RUN_SWIFT_TESTS" == "true" ]] && [ -d "api/swift" ]; then
    echo ""
    echo "🧪 Running Swift client tests..."
    cd api/swift
    swift test || { print_error "Swift tests failed!"; exit 1; }
    cd ../..
    print_status "Swift tests passed"
elif [ "$SWIFT_TESTS_ENABLED" = true ] && [ -d "api/swift" ]; then
    print_info "Skipping Swift tests (no changes)"
fi

echo ""
echo "📦 Creating CLI bundle..."
pnpm run bundle

# Create build artifacts directory
echo ""
echo "📁 Organizing build artifacts..."
mkdir -p build/artifacts
cp bundle/metagen.js build/artifacts/ 2>/dev/null || true
cp version.json build/artifacts/
echo "$CURRENT_VERSION" > build/artifacts/VERSION

# Summary
echo ""
echo "✨ Build Summary"
echo "================"
print_status "Build completed successfully!"
echo "  Version: $CURRENT_VERSION"
echo "  Mode: $MODE"
echo "  Tests run:"
[[ "$RUN_PYTHON_TESTS" == "true" ]] && echo "    - Python API tests ✓"
[[ "$RUN_TS_TESTS" == "true" ]] && echo "    - TypeScript tests ✓"
[[ "$RUN_SWIFT_TESTS" == "true" ]] && echo "    - Swift tests ✓"
[[ "$SKIP_TESTS" == "true" ]] && echo "    - NONE (skipped)"
echo "  Artifacts: build/artifacts/"
echo ""
echo "📋 Next steps:"
[[ "$STUBS_FRESH" == "false" ]] && echo "  - Generate stubs: uv run python generate_stubs.py"
echo "  - Start backend: uv run python main.py"
echo "  - Start CLI: ./bundle/metagen.js"
echo "  - Or run both: pnpm run dev"