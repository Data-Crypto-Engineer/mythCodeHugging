"""State lifecycle: creation, history windows, memory folding, prompt summaries."""
from __future__ import annotations

import json

from models.character import CharacterMemory
from models.game import GameState
from models.learning import LearningProgress
from models.quest import QuestProgress
from models.world import WorldState
from utils.config import get_settings
from utils.validators import scrub_text

RECENT_WINDOW = 8
MAX_LONG_TERM = 14
MAX_LEDGER = 24


def _load_npcs() -> dict:
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "npcs.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def new_game_state(player_name: str, role: str, style: str, seed: str | None = None) -> GameState:
    from core.quest_manager import load_quests, new_quest_progress
    from core.player_model import default_profile

    settings = get_settings()
    quests = load_quests()
    opener = quests["silent_water"]

    characters: dict[str, CharacterMemory] = {}
    for npc_id, data in _load_npcs().items():
        characters[npc_id] = CharacterMemory(
            npc_id=npc_id,
            name=data["name"],
            role=data.get("role", ""),
            disposition=int(data.get("disposition", 0)),
        )

    return GameState(
        story_seed=seed or settings.story_seed,
        player=default_profile(player_name, role, style),
        world=WorldState(),
        quest=new_quest_progress(opener.id),
        learning=LearningProgress(),
        characters=characters,
    )


def snapshot(state: GameState) -> str:
    """Serialise for rollback."""
    return state.model_dump_json()


def restore(state: GameState, snap: str) -> GameState:
    """Roll back to a known-good state after a failed turn."""
    return GameState.model_validate_json(snap)


def append_history(state: GameState, text: str) -> None:
    text = scrub_text(text, 320)
    if not text:
        return
    state.recent_history.append(f"[T{state.turn}] {text}")
    state.recent_history = state.recent_history[-RECENT_WINDOW:]


def add_ledger(state: GameState, text: str) -> None:
    text = scrub_text(text, 200)
    if text and text not in state.ledger:
        state.ledger.append(text)
        state.ledger = state.ledger[-MAX_LEDGER:]


def remember(state: GameState, npc_id: str, note: str) -> None:
    """Attach a memory to the correct character for THIS session."""
    note = scrub_text(note, 220)
    if not note:
        return
    memory = state.characters.get(npc_id)
    if memory is None:
        return
    memory.remember(note)
    memory.last_seen_turn = state.turn
    try:
        from database.storage import get_storage

        get_storage().add_memory(state.session_id, npc_id, note, state.turn)
    except Exception:  # memory is a nicety — never break a turn over it
        pass


def fold_history(state: GameState) -> None:
    """Periodically summarise the recent window into long-term memory.

    This is what keeps prompt size bounded — the whole transcript is never sent.
    """
    if len(state.recent_history) < RECENT_WINDOW:
        return
    oldest = state.recent_history[:3]
    summary = "Earlier: " + " | ".join(item.split("] ", 1)[-1] for item in oldest)
    summary = scrub_text(summary, 260)
    if summary not in state.long_term_memories:
        state.long_term_memories.append(summary)
        state.long_term_memories = state.long_term_memories[-MAX_LONG_TERM:]
    state.recent_history = state.recent_history[3:]


def memory_brief(state: GameState, npc_id: str) -> str:
    """Compact per-character memory for a prompt."""
    memory = state.characters.get(npc_id)
    if memory is None:
        return ""
    notes = "; ".join(memory.memories[-4:]) or "no strong memories yet"
    return f"{memory.name} ({memory.role}) disposition={memory.disposition}. Remembers: {notes}"


def summary_of(state: GameState) -> str:
    """The compact context block handed to agents. Never the full transcript."""
    return (
        f"Turn {state.turn} | Player {state.player.name} the {state.player.role} "
        f"(style: {state.player.style}, confidence {state.player.confidence:.2f})\n"
        f"Quest: {state.quest.title} — {state.quest.objective} "
        f"(stage {state.quest.stage}, path={state.quest.path or 'undecided'})\n"
        f"World: {json.dumps(state.world.as_context(), ensure_ascii=False)}\n"
        f"Learning: active concept '{state.learning.active_concept}', "
        f"mastery {state.player.concept_mastery.for_concept(state.learning.active_concept):.2f}, "
        f"difficulty target {state.learning.next_difficulty}\n"
        f"Long-term memory: {' | '.join(state.long_term_memories[-3:]) or 'none yet'}\n"
        f"Recent: {' | '.join(state.recent_history[-4:]) or 'the story has just begun'}"
    )
