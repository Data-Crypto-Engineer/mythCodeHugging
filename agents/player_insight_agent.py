"""AGENT 2 — Player Insight. Brain: Groq.

Keeps an evolving, evidence-based estimate of preferences and skills. It produces
DELTAS ONLY; `core.player_model` bounds and applies them.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.player import ProfileUpdate
from agents.llm_factory import call_json, reasoner_llm
from core.player_model import apply_update, observe
from utils.config import get_settings
from utils.logger import get_logger

logger = get_logger("insight")

ROLE = "Adaptive Player Insight Analyst"
GOAL = "Maintain a fair, reversible, evidence-based model of how this player prefers to play."
BACKSTORY = (
    "You observe behaviour only. You never diagnose, never label, never infer intelligence, "
    "identity or wellbeing. Every estimate you suggest is small, tentative and reversible."
)

ALLOWED = (
    "exploration_preference, dialogue_preference, puzzle_preference, building_preference, "
    "experimentation, challenge_tolerance, hint_usage"
)


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE,
        goal=GOAL,
        backstory=BACKSTORY,
        verbose=False,
        allow_delegation=False,
        llm=llm or reasoner_llm(),
    )


def _prompt(state: GameState, action_label: str, action_kind: str, outcome: str) -> str:
    profile = state.player
    return (
        "Estimate small preference deltas from ONE observed action.\n"
        f"Action: \"{action_label}\" (kind: {action_kind}). Outcome: {outcome}\n"
        f"Current estimates: exploration={profile.exploration_preference:.2f}, "
        f"dialogue={profile.dialogue_preference:.2f}, puzzle={profile.puzzle_preference:.2f}, "
        f"building={profile.building_preference:.2f}, experimentation={profile.experimentation:.2f}, "
        f"challenge_tolerance={profile.challenge_tolerance:.2f}, hint_usage={profile.hint_usage:.2f}\n"
        f"Recent engagement: {', '.join(profile.recent_engagement) or 'none'}\n\n"
        f"Rules: only these keys may appear in 'deltas': {ALLOWED}. "
        "Each delta is a float in [-0.12, 0.12]. Most actions justify tiny or zero deltas. "
        "Never mention or infer intelligence, mental health, identity, age or any sensitive trait. "
        "'evidence' is a list of short behavioural observations."
    )


def analyse(state: GameState, action_label: str, action_kind: str, outcome: str = "in progress") -> ProfileUpdate | None:
    """Return a ProfileUpdate (or None). Deterministic observation is applied regardless."""
    settings = get_settings()
    if not settings.is_live:
        return None
    update = call_json(reasoner_llm(settings), _prompt(state, action_label, action_kind, outcome), ProfileUpdate, where="insight")
    if update is not None:
        update.deltas = {k: v for k, v in (update.deltas or {}).items() if k in ALLOWED.split(", ")}
    return update


def update_profile(state: GameState, action_label: str, action_kind: str, outcome: str = "in progress") -> GameState:
    """Full agent pass: cheap deterministic evidence first, then bounded LLM deltas."""
    observe(state.player, action_kind)
    update = analyse(state, action_label, action_kind, outcome)
    apply_update(state.player, update)
    return state
