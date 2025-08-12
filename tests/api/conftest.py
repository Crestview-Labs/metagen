"""Fixtures for API tests using real server."""

import time
from pathlib import Path
from typing import Any, AsyncGenerator, Generator

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


@pytest.fixture(scope="session")
def server_process() -> Generator[None, None, None]:
    """Dummy fixture - server should be started manually."""
    # Just check that server is running
    for i in range(10):
        try:
            response = httpx.get("http://localhost:8080/docs")
            if response.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        raise RuntimeError("No server running on port 8080. Start it manually first.")

    yield None


@pytest_asyncio.fixture
async def client(server_process: Any) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an async HTTP client for testing against the real server."""
    async with httpx.AsyncClient(
        base_url="http://localhost:8080", timeout=httpx.Timeout(30.0, read=60.0)
    ) as client:
        yield client
