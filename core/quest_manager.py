"""Quest graph. The Director may propose a direction; the graph bounds it."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.quest import QuestDefinition, QuestProgress

_QUEST_FILE = Path(__file__).resolve().parent.parent / "data" / "quests.json"


def load_quests() -> dict[str, QuestDefinition]:
    with _QUEST_FILE.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = json.load(handle)
    return {item["id"]: QuestDefinition(**item) for item in raw["quests"]}


def new_quest_progress(quest_id: str) -> QuestProgress:
    definition = load_quests()[quest_id]
    return QuestProgress(
        quest_id=definition.id,
        title=definition.title,
        objective=definition.objective,
        location=definition.location,
        concept_hint=definition.concept_hint,
    )


def complete_quest(state) -> QuestProgress:
    """Mark done and advance along the graph. Completions are append-only."""
    current = state.quest
    if current.quest_id and current.quest_id not in state.world.completed_quests:
        state.world.completed_quests.append(current.quest_id)
    definition = load_quests().get(current.quest_id)
    nxt = ""
    if definition:
        nxt = definition.next.get(current.path) or definition.next.get("default") or ""
    if nxt:
        return new_quest_progress(nxt)
    current.status = "completed"
    return current


def set_path(state, path_id: str) -> None:
    """Record the branch the player chose (an append-only, permanent consequence)."""
    if path_id and state.quest.path != path_id:
        state.quest.path = path_id
        from core.state_manager import add_ledger

        add_ledger(state, f"Chose the '{path_id}' road for {state.quest.title}.")


def available_next(quest_id: str) -> list[str]:
    definition = load_quests().get(quest_id)
    if not definition:
        return []
    return [value for key, value in definition.next.items() if key != "default" and value]


def opener_actions(quest_id: str) -> list[dict[str, Any]]:
    definition = load_quests().get(quest_id)
    return list(definition.openers) if definition else []
