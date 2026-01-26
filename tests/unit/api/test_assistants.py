"""Unit tests for assistant management endpoints."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@dataclass
class MockAssistant:
    """Mock assistant ORM object for testing."""

    id: int = 1
    name: str = "Test Assistant"
    description: str = "A test assistant"
    llm_id: int | None = 1
    system_prompt: str = "You are a helpful assistant."
    task_prompt: str = "Help the user."
    starter_messages: list[str] = field(default_factory=lambda: ["Hello!", "How can I help?"])
    is_default: bool = False
    is_visible: bool = True
    display_priority: int = 0
    created_by: int | None = 1
    creation_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_update: datetime | None = None
    user_id_last_update: int | None = None
    deleted_date: datetime | None = None


@dataclass
class MockTokenUser:
    """Mock authenticated user."""

    id: int = 1
    email: str = "test@example.com"
    user_name: str = "testuser"
    first_name: str = "Test"
    last_name: str = "User"
    roles: list[str] = field(default_factory=lambda: ["user"])
    groups: list[str] = field(default_factory=lambda: ["default"])
    external_id: str = "ext-123"


class MockResult:
    """Mock SQLAlchemy query result."""

    def __init__(self, data: list[Any], is_scalar: bool = False):
        self._data = data
        self._is_scalar = is_scalar

    def scalars(self) -> "MockResult":
        return MockResult(self._data, is_scalar=True)

    def all(self) -> list[Any]:
        return self._data

    def scalar_one_or_none(self) -> Any | None:
        return self._data[0] if self._data else None


class MockDbSession:
    """Mock async database session with query tracking."""

    def __init__(self):
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self._query_results: dict[str, list[Any]] = {
            "list": [],      # Main list query results
            "count": [],     # Count query results
            "single": [],    # Single item query results
        }

    def set_list_results(self, results: list[Any]) -> None:
        """Set results for list queries."""
        self._query_results["list"] = results

    def set_count_results(self, count: int) -> None:
        """Set count for count queries."""
        self._query_results["count"] = [(i,) for i in range(count)]

    def set_single_result(self, result: Any | None) -> None:
        """Set result for single item queries."""
        self._query_results["single"] = [result] if result else []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: Any) -> None:
        if hasattr(obj, "id") and obj.id is None:
            obj.id = 1
        if hasattr(obj, "creation_date") and obj.creation_date is None:
            obj.creation_date = datetime.now(timezone.utc)

    async def execute(self, query: Any) -> MockResult:
        query_str = str(query).lower()

        # Detect query type by looking at what's being selected
        if "assistants.id" in query_str and "assistants.name" not in query_str:
            # Count query - only selecting ID
            return MockResult(self._query_results["count"])
        elif "limit" in query_str or "offset" in query_str:
            # List query with pagination
            return MockResult(self._query_results["list"])
        elif "assistants.id =" in query_str or "assistants.id==" in query_str:
            # Single item query
            return MockResult(self._query_results["single"])
        else:
            # Default to list results
            return MockResult(self._query_results["list"])


class TestAssistantEndpoints:
    """Tests for assistant CRUD endpoints."""

    @pytest.fixture
    def mock_user(self) -> MockTokenUser:
        return MockTokenUser()

    @pytest.fixture
    def mock_db(self) -> MockDbSession:
        return MockDbSession()

    @pytest.fixture
    def client(
        self,
        mock_db: MockDbSession,
        mock_user: MockTokenUser,
    ) -> TestClient:
        """Create test client with mocked dependencies."""
        from api.dependencies import get_current_user, get_db_session
        from api.routes.assistants import router

        app = FastAPI()
        app.include_router(router, prefix="/assistants")

        async def override_db() -> AsyncGenerator[MockDbSession, None]:
            yield mock_db

        async def override_user() -> MockTokenUser:
            return mock_user

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_current_user] = override_user

        return TestClient(app)

    def test_list_assistants_empty(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test listing assistants when none exist."""
        mock_db.set_list_results([])
        mock_db.set_count_results(0)

        response = client.get("/assistants")

        assert response.status_code == 200
        data = response.json()
        assert data["assistants"] == []

    def test_list_assistants_with_results(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test listing assistants returns correct data."""
        assistant = MockAssistant()
        mock_db.set_list_results([assistant])
        mock_db.set_count_results(1)

        response = client.get("/assistants")

        assert response.status_code == 200
        data = response.json()
        assert len(data["assistants"]) == 1
        assert data["assistants"][0]["name"] == "Test Assistant"

    def test_list_assistants_with_visibility_filter(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test listing assistants with visibility filter."""
        visible_assistant = MockAssistant(is_visible=True)
        mock_db.set_list_results([visible_assistant])
        mock_db.set_count_results(1)

        response = client.get("/assistants?is_visible=true")

        assert response.status_code == 200
        assert len(response.json()["assistants"]) == 1

    def test_list_assistants_pagination(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test listing assistants with pagination."""
        assistants = [MockAssistant(id=i, name=f"Assistant {i}") for i in range(1, 4)]
        mock_db.set_list_results(assistants)
        mock_db.set_count_results(3)

        response = client.get("/assistants?page=1&limit=2")

        assert response.status_code == 200

    def test_get_assistant_success(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test getting a single assistant by ID."""
        assistant = MockAssistant(id=1)
        mock_db.set_single_result(assistant)

        response = client.get("/assistants/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Assistant"

    def test_get_assistant_not_found(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test getting a non-existent assistant returns 404."""
        mock_db.set_single_result(None)

        response = client.get("/assistants/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Assistant not found"

    def test_create_assistant_success(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test creating a new assistant."""
        response = client.post(
            "/assistants",
            json={
                "name": "New Assistant",
                "description": "A new assistant",
                "system_prompt": "You are helpful.",
                "task_prompt": "Help users.",
                "starter_messages": ["Hi!"],
                "is_default": False,
                "is_visible": True,
                "display_priority": 0,
            },
        )

        assert response.status_code == 201
        assert len(mock_db.added) == 1
        assert mock_db.added[0].name == "New Assistant"

    def test_create_assistant_minimal_fields(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test creating assistant with minimal required fields."""
        response = client.post(
            "/assistants",
            json={
                "name": "Minimal",
                "description": "Minimal description",
                "system_prompt": "Prompt",
                "task_prompt": "Task",
                "starter_messages": [],  # Required due to proto default bug
            },
        )

        assert response.status_code == 201

    def test_update_assistant_success(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test updating an existing assistant."""
        assistant = MockAssistant(id=1)
        mock_db.set_single_result(assistant)

        response = client.put(
            "/assistants/1",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        assert assistant.name == "Updated Name"

    def test_update_assistant_not_found(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test updating a non-existent assistant returns 404."""
        mock_db.set_single_result(None)

        response = client.put(
            "/assistants/999",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404

    def test_update_assistant_partial(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test partial update only changes specified fields."""
        assistant = MockAssistant(id=1, name="Original", description="Original desc")
        mock_db.set_single_result(assistant)

        response = client.put(
            "/assistants/1",
            json={"description": "New description"},
        )

        assert response.status_code == 200
        assert assistant.name == "Original"
        assert assistant.description == "New description"

    def test_delete_assistant_success(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test soft deleting an assistant."""
        assistant = MockAssistant(id=1, deleted_date=None)
        mock_db.set_single_result(assistant)

        response = client.delete("/assistants/1")

        assert response.status_code == 204
        assert assistant.deleted_date is not None

    def test_delete_assistant_not_found(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test deleting a non-existent assistant returns 404."""
        mock_db.set_single_result(None)

        response = client.delete("/assistants/999")

        assert response.status_code == 404

    def test_delete_already_deleted_assistant(
        self,
        client: TestClient,
        mock_db: MockDbSession,
    ) -> None:
        """Test deleting an already-deleted assistant returns 404."""
        mock_db.set_single_result(None)

        response = client.delete("/assistants/1")

        assert response.status_code == 404
