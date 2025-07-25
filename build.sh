#!/bin/bash
set -e

echo "🚀 Building Metagen"
echo "==================="

# Check for required tools
echo "🔍 Checking dependencies..."
command -v uv >/dev/null 2>&1 || { echo "❌ uv is required but not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ node is required but not installed."; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "❌ pnpm is required but not installed. Install with: npm install -g pnpm"; exit 1; }

# Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
uv sync --dev

# Database migrations
echo ""
echo "🗄️  Running database migrations..."
cd db && alembic upgrade head && cd ..

# Frontend dependencies and build
echo ""
echo "📦 Installing frontend dependencies..."
pnpm install

echo ""
echo "🔨 Building TypeScript packages..."
pnpm run build

echo ""
echo "📦 Creating CLI bundle..."
pnpm run bundle

echo ""
echo "🎉 Build completed successfully!"
echo ""
echo "📋 Next steps:"
echo "  - Start backend: uv run python main.py"
echo "  - Start CLI: ./bundle/metagen.js"
echo "  - Or run both: pnpm run dev"