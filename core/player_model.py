"""Bounded, reversible player adaptation.

Hard guarantees (tested):
  * a single action can move any estimate by at most MAX_STEP
  * every estimate stays within [0, 1]
  * confidence rises with evidence and never falls
  * no sensitive attribute is ever produced
"""
from __future__ import annotations

from uuid import uuid4

from models.learning import LearningProgress
from models.player import MAX_STEP, TRACKED_DIMENSIONS, ConceptMastery, PlayerProfile, ProfileUpdate
from utils.validators import clamp

# Deterministic nudge applied from the action kind alone (no LLM needed).
_ACTION_NUDGES = {
    "explore": {"exploration_preference": 0.05, "experimentation": 0.02},
    "talk": {"dialogue_preference": 0.05, "exploration_preference": 0.01},
    "puzzle": {"puzzle_preference": 0.05, "challenge_tolerance": 0.03},
    "build": {"building_preference": 0.06, "experimentation": 0.03},
    "invent": {"building_preference": 0.05, "experimentation": 0.04},
    "travel": {"exploration_preference": 0.04},
    "rest": {},
    "hint": {"hint_usage": 0.06},
    "fail": {"challenge_tolerance": -0.01},
    "solve": {"challenge_tolerance": 0.03, "puzzle_preference": 0.03},
}


def default_profile(name: str, role: str, style: str) -> PlayerProfile:
    return PlayerProfile(
        player_id=uuid4().hex,
        name=name.strip()[:32] or "Wanderer",
        role=role or "Wanderer",
        style=style or "Curious",
    )


def observe(profile: PlayerProfile, action_kind: str) -> PlayerProfile:
    """Cheap deterministic evidence from behaviour alone. Never overrides the LLM."""
    nudges = _ACTION_NUDGES.get(action_kind, {})
    for dimension, delta in nudges.items():
        _bump(profile, dimension, delta)
    profile.evidence_count += 1
    profile.confidence = clamp(profile.confidence + 0.03, 0.0, 1.0, profile.confidence)
    profile.recent_engagement.append(action_kind)
    profile.recent_engagement = profile.recent_engagement[-6:]
    return profile


def apply_update(profile: PlayerProfile, update: ProfileUpdate | None) -> PlayerProfile:
    """Apply the Player Insight Agent's structured deltas, bounded and clamped."""
    if update is None:
        return profile
    for dimension, delta in (update.deltas or {}).items():
        if dimension in TRACKED_DIMENSIONS or dimension == "hint_usage":
            _bump(profile, dimension, delta)
    if update.evidence:
        profile.evidence_count += len(update.evidence)
    profile.confidence = clamp(profile.confidence + 0.05, 0.0, 1.0, profile.confidence)
    return profile


def _bump(profile: PlayerProfile, dimension: str, delta: float) -> None:
    try:
        delta = float(delta)
    except (TypeError, ValueError):
        return
    # MAX_STEP caps a single write; repeated evidence is required for real change.
    delta = max(-MAX_STEP, min(MAX_STEP, delta))
    current = float(getattr(profile, dimension, 0.0))
    setattr(profile, dimension, clamp(current + delta, 0.0, 1.0, current))


def mastery_after(
    profile: PlayerProfile,
    concept: str,
    solved: bool,
    first_try: bool,
    hints_used: int,
) -> PlayerProfile:
    """Mastery moves slowly and can regress — never a permanent label."""
    current = profile.concept_mastery.for_concept(concept)
    if solved and first_try and hints_used == 0:
        gain = 0.30
    elif solved and hints_used == 0:
        gain = 0.20
    elif solved:
        gain = 0.12
    else:
        gain = -0.04
    mastery = getattr(profile.concept_mastery, concept, None)
    if mastery is None and concept not in {"sequence", "conditions", "loops", "code_assembly"}:
        profile.concept_mastery = ConceptMastery(**{**profile.concept_mastery.model_dump(), concept: 0.0})
    profile.concept_mastery.set_concept(concept, clamp(current + gain, 0.0, 1.0, current))
    return profile


def recommend_difficulty(profile: PlayerProfile, learning: LearningProgress) -> int:
    """1..3, driven by demonstrated mastery and challenge tolerance."""
    concept = learning.active_concept
    mastery = profile.concept_mastery.for_concept(concept)
    if mastery >= 0.75 and profile.challenge_tolerance >= 0.5:
        return 3
    if mastery >= 0.45 or profile.challenge_tolerance >= 0.7:
        return 2
    return 1
