#!/bin/bash

# E2E Test Runner for TypeScript and Swift client libraries
# Usage: ./run-e2e-tests.sh [ts|swift|all]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
SERVER_PID_FILE="/tmp/metagen_test_server.pid"
TEST_DB="/tmp/metagen_e2e_test_$(date +%s).db"

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to start test server
start_test_server() {
    print_info "Starting test server..."
    
    # Check if server is already running
    if [ -f "$SERVER_PID_FILE" ]; then
        OLD_PID=$(cat "$SERVER_PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            print_warning "Test server already running with PID $OLD_PID"
            return 0
        else
            rm -f "$SERVER_PID_FILE"
        fi
    fi
    
    # Start server in background
    cd "$ROOT_DIR"
    ./start_server.sh --test > /tmp/metagen_test_server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > "$SERVER_PID_FILE"
    
    # Wait for server to be ready
    print_info "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8080/docs > /dev/null 2>&1; then
            print_success "Server is ready!"
            return 0
        fi
        sleep 1
    done
    
    print_error "Server failed to start within 30 seconds"
    stop_test_server
    exit 1
}

# Function to stop test server
stop_test_server() {
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            print_info "Stopping test server (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            
            # Wait for process to stop
            for i in {1..10}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -9 "$PID" 2>/dev/null || true
            fi
        fi
        rm -f "$SERVER_PID_FILE"
    fi
    
    # Clean up test database
    rm -f "$TEST_DB"
}

# Function to run TypeScript tests
run_typescript_tests() {
    print_info "Running TypeScript E2E tests..."
    cd "$SCRIPT_DIR/api/ts"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        print_info "Installing TypeScript dependencies..."
        npm install
    fi
    
    # Build TypeScript code
    print_info "Building TypeScript code..."
    npm run build
    
    # Run tests
    print_info "Running tests..."
    if npm run test:e2e; then
        print_success "TypeScript tests passed!"
        return 0
    else
        print_error "TypeScript tests failed!"
        return 1
    fi
}

# Function to run Swift tests
run_swift_tests() {
    print_info "Running Swift E2E tests..."
    cd "$SCRIPT_DIR/api/swift"
    
    # Build Swift package
    print_info "Building Swift package..."
    swift build
    
    # Run tests
    print_info "Running tests..."
    if swift test --filter ChatStreamE2ETests; then
        print_success "Swift tests passed!"
        return 0
    else
        print_error "Swift tests failed!"
        return 1
    fi
}

# Cleanup function
cleanup() {
    print_info "Cleaning up..."
    stop_test_server
}

# Set up trap to ensure cleanup on exit
trap cleanup EXIT INT TERM

# Parse arguments
TEST_TARGET="${1:-all}"

# Main execution
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🧪 Metagen E2E Test Runner${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Start test server
start_test_server

# Run tests based on target
case "$TEST_TARGET" in
    ts|typescript)
        run_typescript_tests
        TS_RESULT=$?
        exit $TS_RESULT
        ;;
    swift)
        run_swift_tests
        SWIFT_RESULT=$?
        exit $SWIFT_RESULT
        ;;
    all)
        TS_RESULT=0
        SWIFT_RESULT=0
        
        run_typescript_tests || TS_RESULT=$?
        run_swift_tests || SWIFT_RESULT=$?
        
        echo ""
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}📊 Test Results Summary${NC}"
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        if [ $TS_RESULT -eq 0 ]; then
            print_success "TypeScript tests: PASSED"
        else
            print_error "TypeScript tests: FAILED"
        fi
        
        if [ $SWIFT_RESULT -eq 0 ]; then
            print_success "Swift tests: PASSED"
        else
            print_error "Swift tests: FAILED"
        fi
        
        # Exit with error if any tests failed
        if [ $TS_RESULT -ne 0 ] || [ $SWIFT_RESULT -ne 0 ]; then
            exit 1
        fi
        ;;
    *)
        print_error "Invalid target: $TEST_TARGET"
        echo "Usage: $0 [ts|swift|all]"
        exit 1
        ;;
esac

print_success "All tests completed successfully!"