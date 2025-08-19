#!/bin/bash

# Start server script with optional test mode
# Usage: ./start_server.sh [--test]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default settings
DB_PATH="db/metagen.db"
MODE="production"
PORT=8080

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --test)
            # Test mode: use temporary database in /tmp
            DB_PATH="/tmp/metagen_test_$(date +%s)_$$.db"
            MODE="test"
            echo -e "${YELLOW}🧪 Test mode enabled${NC}"
            echo -e "${YELLOW}📁 Using temporary database: ${DB_PATH}${NC}"
            shift
            ;;
        --port)
            PORT="$2"
            echo -e "${YELLOW}🔌 Using port: ${PORT}${NC}"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --test         Start in test mode with temporary database"
            echo "  --port PORT    Specify port (default: 8080)"
            echo "  --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Start with default database (db/metagen.db)"
            echo "  $0 --test             # Start with temporary database for testing"
            echo "  $0 --test --port 8081 # Start test server on port 8081"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to cleanup on exit (only for test mode)
cleanup() {
    if [ "$MODE" = "test" ] && [ -f "$DB_PATH" ]; then
        echo -e "\n${YELLOW}🧹 Cleaning up temporary database...${NC}"
        rm -f "$DB_PATH"
    fi
}

# Set up cleanup trap for test mode
if [ "$MODE" = "test" ]; then
    trap cleanup EXIT INT TERM
fi

# Display startup information
echo -e "${GREEN}🚀 Starting Metagen Server${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "Mode:     ${MODE}"
echo -e "Database: ${DB_PATH}"
echo -e "Port:     ${PORT}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Start server with uv
uv run python main.py --db-path "${DB_PATH}" --port "${PORT}"