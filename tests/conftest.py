"""Test fixtures. Every test runs OFFLINE: no API keys, no network, no cost."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("MODE", "offline")


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MODE", "offline")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_mythcode.db"))
    for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    from utils.config import get_settings

    get_settings.cache_clear()
    from database.storage import reset_storage_cache

    reset_storage_cache()
    yield
    get_settings.cache_clear()
    reset_storage_cache()


@pytest.fixture
def game(tmp_path):
    from core.state_manager import new_game_state
    from core.state_validator import validate_state

    state = new_game_state("Tester", "Wanderer", "Curious", seed="testseed")
    validate_state(state)
    return state
