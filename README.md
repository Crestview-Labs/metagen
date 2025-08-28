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

### Using the Unified Launch Script (Recommended)

The launch.py script provides a unified interface for all Metagen components with automatic dependency management.

#### Setup
```bash
# Install uv (Python package manager) if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS only: Install XcodeGen for Mac app
brew install xcodegen
```

#### Running Components

```bash
# Start backend server
uv run python launch.py server start

# Stop backend server
uv run python launch.py server stop

# Check server status
uv run python launch.py server status

# Launch CLI (requires backend running)
uv run python launch.py cli

# Launch Mac app (macOS only, requires backend running)
uv run python launch.py macapp

# Launch everything at once (backend + CLI)
uv run python launch.py all
```

#### Profile Support

All components support isolated profiles for different environments:

```bash
# Use a specific profile (default: "default")
uv run python launch.py -p work server start
uv run python launch.py -p work cli

# Profiles are stored in ~/.ambient/profiles/<profile>/
```

#### Features
- **Automatic backend management**: CLI and Mac app connect to existing backend
- **Session management**: Each client gets its own session ID
- **Profile isolation**: Separate data and logs for different use cases
- **Google services**: Optional authentication via `/auth login` in CLI
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

The build.py script manages all build operations with automatic dependency checking.

#### Prerequisites
```bash
# Install uv (Python package manager) if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS only: Install XcodeGen for Mac app
brew install xcodegen
```

#### Using the Build Script

```bash
# Build everything
uv run python build.py --all

# Build specific components
uv run python build.py --api-stubs    # Generate API client stubs
uv run python build.py --ts-api       # Build TypeScript API
uv run python build.py --swift-api    # Build Swift API (macOS only)
uv run python build.py --cli          # Build CLI
uv run python build.py --mac-app      # Build Mac app (macOS only)
uv run python build.py --backend-exe  # Build backend executable with PyInstaller

# Development vs Release builds
uv run python build.py --cli --dev       # Development build
uv run python build.py --cli --release   # Production build

# Version management
uv run python build.py --bump-patch  # Increment patch version (0.1.2 -> 0.1.3)
uv run python build.py --bump-minor  # Increment minor version (0.1.2 -> 0.2.0)
uv run python build.py --bump-major  # Increment major version (0.1.2 -> 1.0.0)

# Testing and validation
uv run python build.py --check-only  # Validate without building
uv run python build.py --test        # Run tests with mocked LLMs
uv run python build.py --test-real   # Run tests with real LLMs
uv run python build.py --type-check  # Run type checking
uv run python build.py --lint        # Run linters

# Package for distribution
uv run python build.py --package-mac  # Package Mac app as DMG
uv run python build.py --package-cli  # Package CLI as distributable

# Clean build artifacts
uv run python build.py --clean

# Verbose mode for debugging
uv run python build.py --mac-app --verbose
```

#### Build Features

- **Dependency checking**: Automatically checks if backend is running when needed
- **Smart rebuilding**: Only rebuilds changed components
- **Force regeneration**: Use `--force-stubs` to regenerate API stubs even if unchanged
- **Parallel builds**: Multiple components can be built together
- **Environment handling**: All Python operations use `uv` automatically

## Architecture

- **Backend**: Python FastAPI server with SQLite storage
- **CLI**: TypeScript/React terminal UI with Ink framework  
- **API**: OpenAPI-based with generated client stubs
- **Tools**: Extensible via MCP (Model Context Protocol)

## Development

### Project Structure
```
metagen/
├── build.py            # Unified build script
├── launch.py           # Unified launch script
├── cli/                # Ambient CLI
│   ├── src/           # TypeScript source
│   └── package.json   # CLI dependencies
├── macapp/            # Mac app (Ambient.app)
│   └── Ambient/       # Swift source
├── api/               # Generated API clients
│   ├── ts/           # TypeScript stubs
│   └── swift/        # Swift stubs
├── agents/           # Agent implementations
├── tools/            # Tool implementations
├── memory/           # Memory system
└── main.py          # Backend entry point
```

### Testing
```bash
# Run all tests with mocked LLMs
uv run python build.py --test

# Run tests with real LLMs
uv run python build.py --test-real

# Run specific test pattern
uv run python build.py --test --test-pattern "test_chat"

# Type checking
uv run python build.py --type-check

# Linting
uv run python build.py --lint

# CLI tests  
cd cli && npm test
```

### Development Workflow

1. **Make changes** to source files
2. **Build** affected components: `uv run python build.py --api-stubs --cli`
3. **Test** your changes: `uv run python build.py --test`
4. **Launch** for manual testing: `uv run python launch.py all`

### Environment Variables

```bash
# Backend configuration
BACKEND_PORT=8080           # Custom backend port (default: 8080)
METAGEN_API_URL=http://...  # Custom API URL for clients

# Testing
TEST_WITH_REAL_LLMS=1       # Use real LLMs in tests

# Profiles
AMBIENT_PROFILE=work        # Use specific profile
```

## License

Proprietary