# Metagen

A superintelligent personal agent system with context-aware memory and tool integration.

## Overview

Metagen is an AI agent framework that provides:
- Persistent conversation memory and context management
- Extensible tool system via Model Context Protocol (MCP)
- Self-healing architecture with automatic error recovery
- Built-in observability and monitoring
- Task planning and autonomous execution

## Requirements

- Python 3.13+
- Node.js 18+
- pnpm (for workspace management)
- uv (Python package manager - install from https://github.com/astral-sh/uv)
- macOS: Xcode and XcodeGen (for Mac app)

## Quick Start

### Ambient CLI (Recommended)

The Ambient CLI provides a unified interface for Metagen with automatic backend management.

#### Setup
```bash
# One-time setup (installs uv, creates Python environment, installs dependencies)
./cli/scripts/ambient-cli.sh setup

# Force recreate environment with latest Python
./cli/scripts/ambient-cli.sh setup --force
```

#### Running
```bash
# Start interactive chat (auto-starts backend if needed)
./cli/scripts/ambient-cli.sh

# Check system status
./cli/scripts/ambient-cli.sh status

# Manage backend server
./cli/scripts/ambient-cli.sh server start
./cli/scripts/ambient-cli.sh server stop
./cli/scripts/ambient-cli.sh server restart
```

#### Features
- **Auto-start**: Backend starts automatically when launching chat
- **Session management**: Each CLI instance gets its own session ID
- **Profile support**: Multiple profiles with isolated data (`-p <profile>`)
- **Google services**: Optional authentication via `/auth login`
- **Advanced text editing**: Ctrl+A/E (home/end), Ctrl+W (delete word), Ctrl+arrows (word navigation)

#### Logs
Backend logs are stored at:
```
~/.ambient/profiles/<profile>/logs/backend-YYYY-MM-DD.log
```

View logs in real-time:
```bash
tail -f ~/.ambient/profiles/default/logs/backend-*.log
```

### Building from Source

#### Prerequisites
```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS only: Install XcodeGen for Mac app
brew install xcodegen

# Set up Python environment
uv venv
uv pip install -r requirements.txt
```

#### Using the Build Script

All builds are managed through the master build script:

```bash
# Build everything (requires backend running on port 8985)
uv run python build.py --all

# Build specific components
uv run python build.py --api-stubs    # Generate API client stubs
uv run python build.py --ts-api       # Build TypeScript API
uv run python build.py --swift-api    # Build Swift API (macOS only)
uv run python build.py --cli          # Build CLI
uv run python build.py --mac-app      # Build Mac app (macOS only)
uv run python build.py --backend-exe  # Build backend executable with PyInstaller
uv run python build.py --package-mac  # Package Mac app as DMG

# Clean all build artifacts
uv run python build.py --clean

# Verbose mode for debugging
uv run python build.py --mac-app -v
```

#### Running Components

##### Backend Server
```bash
# Start backend (required for API stub generation and runtime)
uv run python main.py

# Or with custom port
uv run python main.py --port 8080
```

##### CLI
```bash
# After building with: uv run python build.py --cli
./cli/scripts/ambient-cli.sh
```

##### Mac App (macOS)
```bash
# After building with: uv run python build.py --mac-app
open macapp/build/Build/Products/Release/Ambient.app
```

### Manual Backend Running

If you prefer to run the backend manually:
```bash
# Using uv (after setup)
uv run python main.py

# Or with custom port
uv run python main.py --port 8080
```

## Architecture

- **Backend**: Python FastAPI server with SQLite storage
- **CLI**: TypeScript/React terminal UI with Ink framework  
- **API**: OpenAPI-based with generated client stubs
- **Tools**: Extensible via MCP (Model Context Protocol)

## Development

### Project Structure
```
metagen/
├── cli/                 # Ambient CLI (new unified interface)
│   ├── src/            # TypeScript source
│   └── scripts/        # Build and run scripts
├── packages/cli/       # Original CLI (for reference)
├── api/                # Generated API clients
│   ├── ts/            # TypeScript stubs
│   └── swift/         # Swift stubs
├── agents/            # Agent implementations
├── tools/             # Tool implementations
├── memory/            # Memory system
└── main.py           # Backend entry point
```

### Testing
```bash
# Backend tests
uv run pytest

# CLI tests  
cd cli && npm test
```

## License

Proprietary