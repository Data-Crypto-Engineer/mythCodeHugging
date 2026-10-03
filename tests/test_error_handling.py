"""Missing credentials, malformed AI output, API failure, and state preservation."""
from __future__ import annotations

import pytest

from utils import error_handler as eh
from utils.config import get_settings
from utils.validators import extract_json_block


# ── configuration ───────────────────────────────────────────────
def test_missing_credentials_switch_to_offline():
    settings = get_settings()
    assert settings.has_gemini is False
    assert settings.has_groq is False
    assert settings.mode == "offline"


def test_diagnostics_never_leak_keys():
    settings = get_settings()
    diag = settings.diagnostics()
    assert set(diag) >= {"mode", "gemini_key", "groq_key"}
    assert all("sk-" not in str(value) and "AIza" not in str(value) for value in diag.values())


def test_live_mode_requested_without_keys_degrades(monkeypatch):
    monkeypatch.setenv("MODE", "live")
    get_settings.cache_clear()
    assert get_settings().mode == "offline"


# ── scrubbing ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw",
    [
        "key AIzaSyA1234567890abcdefghijklmnop",
        "Authorization: Bearer gsk_abcdefghijklmnopqrstuvwx",
        "token 0123456789abcdef0123456789abcdef",
    ],
)
def test_scrub_removes_credentials(raw):
    cleaned = eh.scrub(raw)
    assert "[redacted]" in cleaned
    for token in ("AIzaSy", "gsk_", "0123456789abcdef0123456789abcdef"):
        assert token not in cleaned


# ── classification ──────────────────────────────────────────────
def test_auth_errors_are_permanent():
    err = eh.classify(Exception("401 Unauthorized: invalid api key"))
    assert isinstance(err, eh.AuthError)


def test_rate_limits_are_transient():
    err = eh.classify(Exception("429 rate limit exceeded"))
    assert isinstance(err, eh.RateLimitError)


def test_connection_errors_are_transient():
    assert isinstance(eh.classify(ConnectionError("timed out")), eh.ProviderUnavailable)


def test_quota_is_not_retried():
    assert isinstance(eh.classify(Exception("insufficient_quota")), eh.QuotaError)


def test_missing_secret_is_configuration_error():
    assert isinstance(eh.classify(KeyError("GEMINI_API_KEY")), eh.ConfigurationError)


# ── retries ─────────────────────────────────────────────────────
def test_transient_failure_is_retried_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise eh.RateLimitError("429")
        return "ok"

    result = eh.run_with_rescue(flaky, retries=3, backoff=0.0, where="test")
    assert result.ok and result.value == "ok" and calls["n"] == 3


def test_auth_failure_is_never_retried():
    calls = {"n": 0}

    def bad_key():
        calls["n"] += 1
        raise eh.AuthError("401")

    result = eh.run_with_rescue(bad_key, retries=5, backoff=0.0, where="test")
    assert not result.ok and calls["n"] == 1


def test_retries_are_bounded():
    calls = {"n": 0}

    def always_down():
        calls["n"] += 1
        raise eh.ProviderUnavailable("503")

    result = eh.run_with_rescue(always_down, retries=2, backoff=0.0, where="test")
    assert not result.ok and calls["n"] == 3


def test_rescue_never_raises():
    def explode():
        raise ValueError("totally unexpected")

    assert eh.run_with_rescue(explode, retries=1, backoff=0.0, where="test").error is not None


# ── malformed model output ──────────────────────────────────────
def test_extract_json_handles_markdown_fences():
    assert extract_json_block('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_handles_prose_wrapper():
    assert extract_json_block('Sure! Here it is: {"a": 1} — enjoy.') == {"a": 1}


def test_extract_json_returns_none_on_garbage():
    assert extract_json_block("definitely not json") is None
    assert extract_json_block("") is None


def test_call_json_returns_none_on_malformed_output():
    from agents.llm_factory import call_json
    from models.player import ProfileUpdate

    class BadLLM:
        def call(self, prompt):
            return "I refuse to answer in JSON."

    assert call_json(BadLLM(), "prompt", ProfileUpdate, retries=1, where="test") is None


def test_call_json_parses_good_output():
    from agents.llm_factory import call_json
    from models.player import ProfileUpdate

    class GoodLLM:
        def call(self, prompt):
            return '{"deltas": {"puzzle_preference": 0.05}, "evidence": ["tried twice"], "note": "ok"}'

    result = call_json(GoodLLM(), "prompt", ProfileUpdate, retries=1, where="test")
    assert result is not None and result.deltas["puzzle_preference"] == 0.05


def test_call_json_rejects_unknown_keys_and_survives():
    from agents.llm_factory import call_json
    from models.player import ProfileUpdate

    class SloppyLLM:
        def call(self, prompt):
            return '{"deltas": {"intelligence": 1.0}}'

    result = call_json(SloppyLLM(), "prompt", ProfileUpdate, retries=1, where="test")
    assert result is not None
    assert result.deltas == {} or "intelligence" not in result.deltas


# ── state preservation after failure ────────────────────────────
def test_failed_action_preserves_last_valid_state(game):
    from core import game_engine, state_manager

    state = game_engine.opening_scene(game)
    before = state_manager.snapshot(state)
    result = game_engine.act(state, "a_button_that_does_not_exist")
    assert result.scene is not None          # the player always gets a scene
    assert result.errors or result.ok is True
    assert state.world.current_location in state.world.discovered_locations
    restored = state_manager.restore(state, before)
    assert restored.turn == 0 and restored.session_id == state.session_id


def test_turn_result_always_has_a_scene_on_failure(game):
    from core import game_engine

    state = game_engine.opening_scene(game)
    result = game_engine.act(state, "")
    assert result.scene is not None


def test_memory_attached_to_correct_session(game):
    from database.storage import get_storage
    from core.state_manager import remember

    remember(game, "mira", "The player repaired the workshop bench.")
    notes = get_storage().memories_for(game.session_id, "mira")
    assert any("workshop" in note for note in notes)
    assert get_storage().memories_for("a-different-session", "mira") == []


def test_character_memory_cap_keeps_newest():
    from models.character import MAX_NPC_MEMORIES, CharacterMemory

    memory = CharacterMemory(npc_id="mira", name="Mira")
    for index in range(MAX_NPC_MEMORIES + 8):
        memory.remember(f"event {index}")
    assert len(memory.memories) == MAX_NPC_MEMORIES
    assert "event 20" in memory.memories[-1]


def test_state_round_trip_is_lossless(game):
    from models.game import GameState

    again = GameState.model_validate_json(game.model_dump_json())
    assert again == game
