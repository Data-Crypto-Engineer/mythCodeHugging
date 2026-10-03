from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from models.character import CharacterMemory
from models.learning import ConceptReveal, Invention, LearningProgress, PuzzlePrompt
from models.player import PlayerProfile
from models.quest import QuestProgress
from models.story import SafetyVerdict, Scene
from models.world import WorldState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GameState(BaseModel):
    """The single persistent truth for one playthrough."""
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    turn: int = 0
    story_seed: str = "eldertree"
    player: PlayerProfile
    world: WorldState = Field(default_factory=WorldState)
    quest: QuestProgress
    learning: LearningProgress = Field(default_factory=LearningProgress)
    characters: dict[str, CharacterMemory] = Field(default_factory=dict)
    recent_history: list[str] = Field(default_factory=list)   # compact window
    long_term_memories: list[str] = Field(default_factory=list)  # summarised
    ledger: list[str] = Field(default_factory=list)
    inventions: list[Invention] = Field(default_factory=list)
    last_scene: Scene | None = None


class TurnResult(BaseModel):
    """What one player action produced. Always returned — never a raw exception."""
    ok: bool = True
    scene: Scene | None = None
    messages: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    puzzle: PuzzlePrompt | None = None
    puzzle_result: str = ""
    reveal: ConceptReveal | None = None
    safety: SafetyVerdict | None = None
    debug: list[str] = Field(default_factory=list)
    state_changed: bool = False
