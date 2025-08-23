# Ambient CLI

Unified command-line interface for Metagen that manages both the backend server and provides an interactive chat interface.

## Features

- 🚀 **Single Command**: Start everything with `ambient cli`
- 🔄 **Automatic Backend Management**: Backend starts/stops automatically
- 👥 **Profile Support**: Run multiple isolated instances
- 📝 **Log Management**: View and stream backend logs
- 🏥 **Health Monitoring**: Automatic recovery from crashes
- 🎯 **Zero Configuration**: Works out of the box

## Installation

```bash
# Install dependencies
pnpm install

# Build the CLI
pnpm build

# Link globally (for development)
npm link
```

## Usage

### Quick Start

```bash
# Start interactive chat (default)
ambient cli

# Use a different profile
ambient --profile dev cli
```

### Profile Management

```bash
# List all profiles
ambient profiles list

# Create a new profile
ambient profiles create myprofile

# Delete a profile
ambient profiles delete myprofile

# Show profile details
ambient profiles show myprofile
```

### Log Management

```bash
# Show recent logs
ambient logs

# Stream logs in real-time
ambient logs --follow

# Show last N lines
ambient logs --tail 100

# Filter by log level
ambient logs --level ERROR
```

### Server Mode (Advanced)

```bash
# Run backend only
ambient server

# Run with specific profile
ambient server --profile production

# Run on custom port
ambient server --port 9000
```

## Development

### Project Structure

```
cli/
├── src/
│   ├── backend/         # Backend management
│   ├── commands/        # CLI commands
│   ├── utils/          # Utilities
│   └── types/          # TypeScript types
├── tests/
│   ├── unit/           # Unit tests
│   ├── integration/    # Integration tests
│   └── e2e/            # End-to-end tests
└── dist/               # Compiled output
```

### Building

```bash
# Build TypeScript
pnpm build

# Watch mode for development
pnpm dev
```

### Testing

```bash
# Run all tests
pnpm test

# Run specific test suites
pnpm test:unit
pnpm test:integration
pnpm test:e2e

# Watch mode
pnpm test:watch

# Coverage report
pnpm coverage
```

### Code Quality

```bash
# Type checking
pnpm typecheck

# Linting
pnpm lint

# Formatting
pnpm format
```

## Configuration

Each profile has its own configuration file at `~/.ambient/profiles/{name}/config.yaml`:

```yaml
profile: default
backend:
  port: 8080
  host: 127.0.0.1
  log_level: INFO
  
cli:
  theme: dark
  
tools:
  auto_approve:
    - read_file
    - list_files
  require_approval: true
```

### Environment Variables

```bash
AMBIENT_PROFILE=dev          # Default profile to use
AMBIENT_CONFIG_DIR=~/.ambient # Configuration directory
AMBIENT_LOG_LEVEL=DEBUG       # Log level
AMBIENT_PORT=9000            # Override backend port
```

## Profile Structure

Each profile maintains isolated:
- **Database**: `~/.ambient/profiles/{name}/data/metagen.db`
- **Logs**: `~/.ambient/profiles/{name}/logs/`
- **Configuration**: `~/.ambient/profiles/{name}/config.yaml`
- **PID File**: `~/.ambient/profiles/{name}/ambient.pid`

## Architecture

The Ambient CLI consists of several key components:

1. **BackendManager**: Manages Python backend lifecycle
2. **ProfileManager**: Handles multiple isolated instances
3. **HealthMonitor**: Monitors backend health
4. **LogManager**: Handles log viewing and rotation
5. **ProcessManager**: Low-level process control

## Troubleshooting

### Backend won't start
- Check if port is already in use
- Verify Python and uv are installed
- Check logs for errors

### Profile issues
- Ensure profile name is valid
- Check disk space for database
- Verify permissions on config directory

### Connection problems
- Check backend health: `ambient status`
- Verify network settings
- Check firewall rules

## Contributing

1. Follow TypeScript best practices
2. Write tests for new features
3. Update documentation
4. Run tests before committing

## License

MIT