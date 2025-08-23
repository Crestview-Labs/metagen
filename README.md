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
- uv (automatically installed by CLI setup)

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

#### Generate API Stubs
```bash
./build.sh  # Generates TypeScript and Swift client stubs
```

#### Build CLI
```bash
cd cli
npm install
npm run build
```

#### Package for Distribution (macOS)
```bash
./cli/scripts/build-macos.sh
# Creates distributable in cli/dist-macos/
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