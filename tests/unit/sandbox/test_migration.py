"""Smoke tests for sandbox migration file."""

from pathlib import Path

import pytest


MIGRATION_FILE = Path(
    "src/migration/migrations/versions/20260216_120000_add_sandbox_tables.py"
)


class TestSandboxMigration:
    """Smoke tests for migration file structure."""

    def test_migration_file_exists(self) -> None:
        """Test that the migration file exists."""
        assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"

    def test_migration_has_revision(self) -> None:
        """Test that migration has proper revision ID."""
        content = MIGRATION_FILE.read_text()
        assert "revision = '20260216_120000'" in content

    def test_migration_has_down_revision(self) -> None:
        """Test that migration references correct parent."""
        content = MIGRATION_FILE.read_text()
        assert "down_revision = '20260210_033000'" in content

    def test_migration_creates_sandbox_sessions(self) -> None:
        """Test that migration creates sandbox_sessions table."""
        content = MIGRATION_FILE.read_text()
        assert "CREATE TABLE IF NOT EXISTS sandbox_sessions" in content

    def test_migration_creates_sandbox_events(self) -> None:
        """Test that migration creates sandbox_events table."""
        content = MIGRATION_FILE.read_text()
        assert "CREATE TABLE IF NOT EXISTS sandbox_events" in content

    def test_migration_uses_timestamptz(self) -> None:
        """Test that migration uses TIMESTAMPTZ (not TIMESTAMP)."""
        content = MIGRATION_FILE.read_text()
        assert "TIMESTAMPTZ" in content
        # Ensure no bare TIMESTAMP (without TZ)
        lines = content.split("\n")
        for line in lines:
            if "TIMESTAMP" in line and "TIMESTAMPTZ" not in line:
                # Allow "Timestamp" in proto imports and comments
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if "google.protobuf.Timestamp" in line:
                    continue
                # This would be a bare TIMESTAMP column - fail
                # But we need to be careful about the word appearing in comments
                if "TIMESTAMP" in stripped and "TIMESTAMPTZ" not in stripped:
                    # Check it's actually in a CREATE/ALTER statement
                    if any(kw in stripped.upper() for kw in ("CREATE", "ALTER", "DEFAULT")):
                        pytest.fail(
                            f"Found bare TIMESTAMP (should be TIMESTAMPTZ): {stripped}"
                        )

    def test_migration_has_indexes(self) -> None:
        """Test that migration creates expected indexes."""
        content = MIGRATION_FILE.read_text()
        assert "ix_sandbox_sessions_user_created" in content
        assert "ix_sandbox_sessions_status_active" in content
        assert "ix_sandbox_sessions_container_id" in content
        assert "ix_sandbox_events_session_created" in content
        assert "ix_sandbox_events_type_created" in content

    def test_migration_has_downgrade(self) -> None:
        """Test that migration has a downgrade function."""
        content = MIGRATION_FILE.read_text()
        assert "def downgrade()" in content
        assert "DROP TABLE IF EXISTS sandbox_events" in content
        assert "DROP TABLE IF EXISTS sandbox_sessions" in content

    def test_migration_is_idempotent(self) -> None:
        """Test that migration uses IF NOT EXISTS for idempotency."""
        content = MIGRATION_FILE.read_text()
        assert "IF NOT EXISTS" in content

    def test_migration_has_foreign_keys(self) -> None:
        """Test that migration has proper foreign key references."""
        content = MIGRATION_FILE.read_text()
        assert "REFERENCES users(id)" in content
        assert "REFERENCES chat_sessions(id)" in content
        assert "REFERENCES sandbox_sessions(id)" in content
