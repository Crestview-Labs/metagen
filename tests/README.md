# Metagen Test Suite

This directory contains comprehensive tests for the Metagen project, including unit tests, integration tests, and LLM provider tests.

## Test Structure

```
tests/
├── client/                    # Client tests
│   ├── test_agentic_client.py # AgenticClient with tool calling
│   ├── test_factory.py        # LLM client factory tests
│   └── llm_providers/         # Provider-specific tests
│       ├── test_anthropic_client.py
│       ├── test_openai_client.py
│       └── test_gemini_client.py
├── memory/                    # Memory system tests
├── conftest.py               # Pytest configuration and fixtures
└── README.md                 # This file
```

## Test Markers

We use pytest markers to categorize tests:

- `@pytest.mark.unit` - Unit tests with mocked dependencies
- `@pytest.mark.integration` - Integration tests  
- `@pytest.mark.llm` - Tests that make actual LLM API calls (require API keys)
- `@pytest.mark.memory` - Memory system tests
- `@pytest.mark.asyncio` - Async tests (auto-applied)

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run only unit tests (no API keys needed)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only LLM tests (requires API keys)
pytest -m llm

# Run specific test file
pytest tests/client/test_agentic_client.py

# Run specific test class or method
pytest tests/client/test_agentic_client.py::TestAgenticClient::test_tool_calling_integration
```

### API Keys Configuration

The test suite automatically loads API keys from the `.env` file in the project root (handled by `load_dotenv()` in conftest.py).

Create a `.env` file in the project root:
```bash
# .env file in project root
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```

Alternatively, you can set environment variables:
```bash
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export GEMINI_API_KEY="your-key"
```

Tests requiring API keys will automatically skip if the keys are not available.

### Coverage Reports

```bash
# Generate coverage report
pytest --cov=. --cov-report=html --cov-report=term

# Open HTML coverage report
open htmlcov/index.html

# Coverage for specific modules
pytest --cov=client --cov=agents --cov-report=html
```

### Parallel Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
pytest -n auto

# Run with 4 workers
pytest -n 4
```

### Debugging Tests

```bash
# Drop into debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Show full assertion details
pytest -vv

# Stop on first failure
pytest -x
```

## Test Fixtures

Key fixtures available in `conftest.py`:

- `require_anthropic_key` - Skip test if Anthropic API key not available
- `require_openai_key` - Skip test if OpenAI API key not available  
- `require_gemini_key` - Skip test if Gemini API key not available
- `require_all_llm_keys` - Skip test if any LLM API key is missing
- `temp_db_path` - Temporary database for testing
- `storage_backend` - SQLite backend for memory tests
- `memory_manager` - Memory manager instance

## Writing New Tests

### Unit Test Example

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_conversion(self):
    """Test message format conversion."""
    # Use mocks for external dependencies
    mock_client = AsyncMock()
    # Test internal logic
    assert result == expected
```

### LLM Test Example

```python
@pytest.mark.llm
@pytest.mark.asyncio
async def test_real_generation(self, require_anthropic_key):
    """Test with real Anthropic API."""
    client = AnthropicClient()
    await client.initialize()
    try:
        response = await client.generate(messages)
        assert response.content
    finally:
        await client.close()
```

## CI/CD Integration

For CI/CD pipelines, run only unit tests by default:

```bash
# In CI pipeline
pytest -m "unit and not llm"
```

Run LLM tests in a separate job with secrets:

```bash
# In separate CI job with secrets
pytest -m llm
```

## Test Organization Best Practices

1. **Use appropriate markers** - Always mark tests with `unit`, `integration`, or `llm`
2. **Mock external dependencies** - Unit tests should not make network calls
3. **Use fixtures** - Leverage the API key fixtures for LLM tests
4. **Clean up resources** - Always close clients and clean up files in finally blocks
5. **Test both success and failure cases** - Include error handling tests

## Troubleshooting

### Import Errors

Ensure you're running from the project root:
```bash
cd /path/to/metagen
pytest
```

### Async Test Issues

Tests use `pytest-asyncio` with auto mode. If you see async warnings:
```bash
pip install -U pytest-asyncio
```

### API Key Issues

Tests will skip if API keys are missing. To see which keys are missing:
```bash
pytest -v -m llm -s
```

The skip messages will show which API keys are missing.

### Rate Limiting

LLM tests may hit rate limits. Consider:
- Running tests sequentially: `pytest -n 0`
- Adding delays between tests
- Using test-specific API keys with higher limits

### Memory/Database Tests

Memory tests use temporary SQLite databases. If you see lock errors:
```bash
# Run memory tests sequentially
pytest -m memory -n 0
```