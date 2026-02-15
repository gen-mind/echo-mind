"""
Unit tests for tool policy profiles.

Tests cover profile definitions, immutability, and correctness of all
four named presets: minimal, coding, messaging, full.
Target: 100% code coverage.
"""

import pytest
from dataclasses import FrozenInstanceError

from src.agent.policy.profiles import PROFILES, ProfileDef


class TestProfileDef:
    """Tests for ProfileDef dataclass."""

    def test_frozen_immutability(self) -> None:
        """Test that ProfileDef instances are frozen (immutable)."""
        profile = ProfileDef(allow=["read"], deny=[])
        with pytest.raises(FrozenInstanceError):
            profile.allow = ["write"]  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            profile.deny = ["bash"]  # type: ignore[misc]

    def test_profile_def_creation(self) -> None:
        """Test creating a ProfileDef with custom values."""
        profile = ProfileDef(allow=["tool_a", "tool_b"], deny=["tool_c"])
        assert profile.allow == ["tool_a", "tool_b"]
        assert profile.deny == ["tool_c"]


class TestProfiles:
    """Tests for the PROFILES dictionary."""

    def test_all_four_profiles_exist(self) -> None:
        """Test that all four expected profiles are defined."""
        expected = {"minimal", "coding", "messaging", "full"}
        assert set(PROFILES.keys()) == expected

    def test_profiles_count(self) -> None:
        """Test that exactly four profiles are defined."""
        assert len(PROFILES) == 4

    def test_all_profiles_are_profile_def(self) -> None:
        """Test that all profile values are ProfileDef instances."""
        for name, profile in PROFILES.items():
            assert isinstance(profile, ProfileDef), (
                f"Profile '{name}' is not a ProfileDef"
            )

    def test_minimal_profile(self) -> None:
        """Test minimal profile allows only read-only tools."""
        profile = PROFILES["minimal"]
        expected_allow = ["read", "grep", "glob", "git_log", "git_diff", "git_status"]
        assert profile.allow == expected_allow
        assert profile.deny == []

    def test_coding_profile(self) -> None:
        """Test coding profile allows dev tools."""
        profile = PROFILES["coding"]
        assert profile.allow == ["read", "write", "grep", "glob", "bash", "git_*"]
        assert profile.deny == []

    def test_messaging_profile(self) -> None:
        """Test messaging profile denies all tools."""
        profile = PROFILES["messaging"]
        assert profile.allow == []
        assert profile.deny == ["*"]

    def test_full_profile(self) -> None:
        """Test full profile allows all tools."""
        profile = PROFILES["full"]
        assert profile.allow == ["*"]
        assert profile.deny == []
