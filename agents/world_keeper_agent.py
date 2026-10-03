"""AGENT 4 — World Keeper. Brain: Groq.

Maintains continuity, proposes world changes and writes character memories.
It cannot save anything: `core.state_validator.validate_changes` gates every value.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.story import Scene
from models.world import WorldPatch
from agents.llm_factory import call_json, reasoner_llm
from utils.config import get_settings
from utils.logger import get_logger

logger = get_logger("world")

ROLE = "World Keeper of Elarion"
GOAL = "Guard continuity: keep locations, resources, NPC states and memories consistent with everything that has happened."
BACKSTORY = (
    "You are the archivist of a kingdom. You never contradict an established fact, and you would rather "
    "propose no change than an inconsistent one."
)


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE, goal=GOAL, backstory=BACKSTORY, verbose=False, allow_delegation=False, llm=llm or reasoner_llm()
    )


def _prompt(state: GameState, scene: Scene, action_label: str) -> str:
    return (
        "You are the continuity engine. Read the scene and decide what, if anything, changes in the world.\n"
        f"PLAYER ACTION: \"{action_label}\"\n"
        f"SCENE: {scene.title} — {scene.description}\n"
        f"CURRENT WORLD: water={state.world.water_supply}, spirit_trust={state.world.forest_spirit_trust}, "
        f"guardian={state.world.clockwork_guardian}, morale={state.world.village_morale}, "
        f"energy={state.world.energy_reserve}, location={state.world.current_location}\n"
        f"KNOWN LOCATIONS: {', '.join(state.world.discovered_locations)}\n"
        f"COMPLETED QUESTS: {', '.join(state.world.completed_quests) or 'none'}\n\n"
        "Rules:\n"
        "- Allowed 'changes' keys ONLY: water_supply (damaged|redirected|restored), forest_spirit_trust (int), "
        "clockwork_guardian (inactive|stirring|active|awakened), village_morale (int 0..100), "
        "energy_reserve (int 0..100), current_location (must already be known).\n"
        "- Never propose a change that undoes a previous decision, and never more than 2 changes.\n"
        "- 'memory_notes' may record at most 1 durable fact about the player for a specific npc_id.\n"
        "- 'open_threads' lists unresolved consequences for the story to pick up later.\n"
        "- Keep 'continuity_note' to one sentence."
    )


def propose(state: GameState, scene: Scene, action_label: str) -> WorldPatch | None:
    settings = get_settings()
    if not settings.is_live:
        return None
    return call_json(reasoner_llm(settings), _prompt(state, scene, action_label), WorldPatch, where="world")


def offline_patch(state: GameState, scene: Scene, action_label: str) -> WorldPatch:
    """Deterministic continuity pass used offline and in tests."""
    from models.world import MemoryNote

    notes: list[MemoryNote] = []
    text = f"{scene.description} {action_label}".lower()
    if scene.characters:
        npc_id = scene.characters[0]
        if npc_id in state.characters:
            verb = "helped" if any(word in text for word in ("repair", "help", "build")) else "spoke with"
            notes.append(MemoryNote(npc_id=npc_id, note=f"The player {verb} {state.characters[npc_id].name} about the silent water."))
    threads = []
    if state.world.water_supply != "restored":
        threads.append("The waterwheel is still silent.")
    return WorldPatch(
        changes=[],
        memory_notes=notes,
        open_threads=threads,
        continuity_note="Deterministic continuity pass; no world values were changed this turn.",
    )
