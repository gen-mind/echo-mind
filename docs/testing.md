# Testing Guide

> How to run and write tests for EchoMind services.

---

## Quick Start

```bash
# Run all unit tests
python -m pytest tests/unit/ -v

# Run tests for a specific service
python -m pytest tests/unit/api/ -v

# Run a specific test file
python -m pytest tests/unit/api/test_connectors.py -v

# Run a specific test
python -m pytest tests/unit/api/test_connectors.py::TestConnectorEndpoints::test_create_connector_success -v
```

---

## Test Structure

```
tests/
├── unit/                    # Unit tests (mocked dependencies)
│   ├── api/                 # API route tests
│   │   ├── test_assistants.py
│   │   ├── test_connectors.py
│   │   ├── test_documents.py
│   │   └── test_health.py
│   ├── embedder/            # Embedder service tests
│   ├── semantic/            # Semantic service tests
│   └── ...
├── integration/             # Integration tests (real dependencies)
└── conftest.py              # Shared fixtures
```

---

## Running Tests

### Basic Commands

| Command | Description |
|---------|-------------|
| `pytest tests/unit/` | Run all unit tests |
| `pytest tests/unit/api/` | Run API tests only |
| `pytest -v` | Verbose output (show test names) |
| `pytest -vv` | Extra verbose (show assertion details) |
| `pytest -x` | Stop on first failure |
| `pytest --tb=short` | Shorter tracebacks |
| `pytest --tb=no` | No tracebacks |

### With Coverage

```bash
# Run with coverage report
python -m pytest tests/unit/ --cov=src --cov-report=term-missing

# Generate HTML coverage report
python -m pytest tests/unit/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

### Filtering Tests

```bash
# Run tests matching a pattern
pytest -k "connector"           # Tests with "connector" in name
pytest -k "create or delete"    # Tests with "create" OR "delete"
pytest -k "not slow"            # Exclude tests marked as slow

# Run tests by marker
pytest -m "unit"                # Only @pytest.mark.unit tests
pytest -m "not integration"     # Exclude integration tests
```

### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto                  # Use all CPU cores
pytest -n 4                     # Use 4 workers
```

---

## Writing Tests

### API Route Tests

Use FastAPI's `TestClient` with dependency overrides:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session
from api.routes.connectors import router


class TestConnectorEndpoints:
    @pytest.fixture
    def client(self, mock_db, mock_user):
        app = FastAPI()
        app.include_router(router, prefix="/connectors")

        async def override_db():
            yield mock_db

        async def override_user():
            return mock_user

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_current_user] = override_user

        return TestClient(app)

    def test_list_connectors(self, client, mock_db):
        mock_db.set_list_results([])
        response = client.get("/connectors")
        assert response.status_code == 200
```

### Mock Database Session

Create mock sessions that return predictable results:

```python
from dataclasses import dataclass, field

@dataclass
class MockConnector:
    """Mock ORM object - use string values for enums."""
    id: int = 1
    name: str = "Test Connector"
    type: str = "google_drive"      # String, not enum
    status: str = "active"          # String, not enum
    user_id: int = 1


class MockDbSession:
    def __init__(self):
        self._results = {"list": [], "single": None}

    def set_list_results(self, results):
        self._results["list"] = results

    def set_single_result(self, result):
        self._results["single"] = result

    async def execute(self, query):
        # Detect query type and return appropriate mock
        query_str = str(query).lower()
        if "limit" in query_str:
            return MockResult(self._results["list"])
        return MockResult([self._results["single"]] if self._results["single"] else [])
```

### Testing Async Code

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected
```

---

## Common Patterns

### ORM vs Pydantic Enums

The ORM stores enum values as strings, but Pydantic models expect enum types. Use converters:

```python
# In tests, mock ORM objects use strings
mock_connector = MockConnector(type="google_drive", status="active")

# The API uses converters to transform to Pydantic enums
from api.converters import orm_to_connector
connector = orm_to_connector(mock_connector)
# connector.type == ConnectorType.CONNECTOR_TYPE_GOOGLE_DRIVE
```

### Request Body Enums

When testing POST/PUT requests, use integer enum values:

```python
def test_create_connector(self, client):
    response = client.post("/connectors", json={
        "name": "New Connector",
        "type": 2,      # CONNECTOR_TYPE_GOOGLE_DRIVE
        "scope": 1,     # CONNECTOR_SCOPE_USER
    })
    assert response.status_code == 201
```

Enum value reference (from proto definitions):
- `ConnectorType`: 0=UNSPECIFIED, 1=TEAMS, 2=GOOGLE_DRIVE, 3=ONEDRIVE, 4=WEB, 5=FILE
- `ConnectorScope`: 0=UNSPECIFIED, 1=USER, 2=GROUP, 3=ORG
- `ConnectorStatus`: 0=UNSPECIFIED, 1=PENDING, 2=SYNCING, 3=ACTIVE, 4=ERROR, 5=DISABLED

---

## Debugging Failed Tests

```bash
# Show print statements
pytest -s

# Show local variables on failure
pytest -l

# Drop into debugger on failure
pytest --pdb

# Run only last failed tests
pytest --lf

# Run failed tests first
pytest --ff
```

---

## CI/CD Integration

Tests run automatically on:
- Pull request creation
- Push to main branch

Required pass rate: **100%** for unit tests before merge.

```bash
# CI command
python -m pytest tests/unit/ -v --tb=short --cov=src --cov-fail-under=70
```

---

## Troubleshooting

### Import Errors

Ensure `PYTHONPATH` includes `src/`:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
# or
PYTHONPATH=src pytest tests/unit/
```

### Async Warnings

If you see `RuntimeWarning: coroutine was never awaited`, ensure:
1. Test function is marked with `@pytest.mark.asyncio`
2. You're using `await` on async calls

### Database Connection Errors

Unit tests should never connect to real databases. If you see connection errors, the mock isn't being applied. Check:
1. Dependency override is set correctly
2. Override function signature matches the original

---

## References

- [pytest documentation](https://docs.pytest.org/)
- [FastAPI testing guide](https://fastapi.tiangolo.com/tutorial/testing/)
- `.claude/rules/testing.md` - Testing standards
