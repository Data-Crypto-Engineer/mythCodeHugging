"""Pydantic contracts. Every agent boundary is typed here — no loose dicts."""
from models.character import CharacterMemory, NPCProfile
from models.game import GameState, TurnResult
from models.learning import (
    ConceptReveal,
    Invention,
    InventionBlock,
    LearningFrame,
    LearningProgress,
    LearningRecord,
    PuzzleHint,
    PuzzlePrompt,
    PuzzleResult,
)
from models.player import ConceptMastery, PlayerProfile, ProfileUpdate
from models.quest import QuestDefinition, QuestProgress
from models.story import DialogueLine, DirectorPlan, SafetyVerdict, Scene, SceneAction
from models.world import MemoryNote, ProposedChange, WorldPatch, WorldState

__all__ = [
    "CharacterMemory", "NPCProfile", "GameState", "TurnResult",
    "ConceptReveal", "Invention", "InventionBlock", "LearningFrame",
    "LearningProgress", "LearningRecord", "PuzzleHint", "PuzzlePrompt", "PuzzleResult",
    "ConceptMastery", "PlayerProfile", "ProfileUpdate",
    "QuestDefinition", "QuestProgress",
    "DialogueLine", "DirectorPlan", "SafetyVerdict", "Scene", "SceneAction",
    "MemoryNote", "ProposedChange", "WorldPatch", "WorldState",
]
