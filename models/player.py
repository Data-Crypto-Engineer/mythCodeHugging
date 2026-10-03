"""Adaptive Player Model.

Reversible, evidence-based estimates only. Nothing here may encode intelligence,
mental health, identity, or any sensitive personal characteristic.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

TRACKED_DIMENSIONS = (
    "exploration_preference",
    "dialogue_preference",
    "puzzle_preference",
    "building_preference",
    "experimentation",
    "challenge_tolerance",
)
MAX_STEP = 0.12  # a single action may move any estimate by at most this much


class ConceptMastery(BaseModel):
    model_config = ConfigDict(extra="allow")
    sequence: float = 0.0
    conditions: float = 0.0
    loops: float = 0.0
    code_assembly: float = 0.0

    def for_concept(self, concept: str) -> float:
        return float(getattr(self, concept, 0.0) or 0.0)

    def set_concept(self, concept: str, value: float) -> None:
        setattr(self, concept, round(max(0.0, min(1.0, value)), 4))


class PlayerProfile(BaseModel):
    player_id: str
    name: str
    role: str = "Wanderer"
    style: str = "Curious"
    # estimates in [0, 1]
    exploration_preference: float = 0.5
    dialogue_preference: float = 0.5
    puzzle_preference: float = 0.5
    building_preference: float = 0.4
    experimentation: float = 0.5
    challenge_tolerance: float = 0.5
    hint_usage: float = 0.0
    # adaptive controls
    confidence: float = 0.15          # rises as evidence accumulates
    challenge_level: int = 1
    concept_mastery: ConceptMastery = Field(default_factory=ConceptMastery)
    recent_engagement: list[str] = Field(default_factory=list)
    evidence_count: int = 0


class ProfileUpdate(BaseModel):
    """Structured output of the Player Insight Agent."""
    deltas: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    note: str = ""
