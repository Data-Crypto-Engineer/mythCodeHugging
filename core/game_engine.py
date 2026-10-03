"""Thin application-facing facade over the Flow.

`app.py` talks to this module and nothing else, which keeps Streamlit concerns
out of the agent layer and makes the whole engine testable without a browser.
"""
from __future__ import annotations

from typing import Any

from models.game import GameState, TurnResult
from utils.logger import get_logger

logger = get_logger("engine")


def new_session(name: str, role: str, style: str) -> GameState:
    from core.state_manager import new_game_state

    state = new_game_state(name, role, style)
    _save(state)
    return state


def opening_scene(state: GameState) -> GameState:
    """Seed the very first scene without a player action."""
    from agents.continuity_safety_agent import safe_scene
    from models.story import Scene, SceneAction
    from core.quest_manager import opener_actions
    from core.state_manager import append_history

    actions = [
        SceneAction(action_id=opener["id"], label=opener["label"], kind=opener["kind"])
        for opener in opener_actions(state.quest.quest_id)[:4]
    ]
    state.last_scene = Scene(
        title="The Water Has Stopped",
        description=(
            "Whispering Village smells of dust where it should smell of wet stone. The great wheel "
            "above the river stands still, its buckets dry, and the villagers have begun to carry "
            "buckets in pairs as if the silence might hear them. You have just arrived, and everyone "
            "has already decided that you are the kind of person who might fix things. The river "
            "murmurs something you cannot quite hear."
        ),
        dialogue=[
            {"speaker": "Brack", "text": "Water's gone. Talk fast, I'm carrying."},
            {"speaker": "Elowen", "text": "Are you the one who's going to fix it? Everyone says someone will."},
        ],
        actions=actions,
        consequence_preview="The wheel is not merely broken. It is waiting for a reason.",
        characters=["brack", "elowen"],
        category="exploration",
        location=state.world.current_location,
    )
    append_history(state, "Arrived in Whispering Village; the waterwheel stands silent.")
    _save(state)
    return state


def act(state: GameState, action_id: str, submission: dict[str, Any] | None = None) -> TurnResult:
    from agents.mythcode_crew import process_player_action

    result = process_player_action(state, action_id, submission)
    _save(state)
    return result


def craft_invention(state: GameState, name: str, blocks: list[dict[str, Any]]) -> str:
    """Player-created magical invention — deterministic, safe, no code execution."""
    from core.learning_engine import compose_invention
    from core.state_manager import add_ledger, append_history
    from database.storage import get_storage

    invention = compose_invention(name, blocks, state.turn)
    state.inventions.append(invention)
    add_ledger(state, f"Built the device '{invention.name}': {invention.effect}")
    append_history(state, f"Crafted '{invention.name}' at {state.world.current_location}.")
    get_storage().save_game(state)
    return invention.effect


def travel_to(state: GameState, location: str) -> bool:
    """Discovery is append-only; travel only to places already discovered."""
    from core.state_manager import add_ledger

    if location not in state.world.discovered_locations:
        return False
    state.world.current_location = location
    add_ledger(state, f"Travelled to {location}.")
    _save(state)
    return True


def discover(state: GameState, location: str) -> None:
    if location and location not in state.world.discovered_locations:
        state.world.discovered_locations.append(location)
        from core.state_manager import add_ledger

        add_ledger(state, f"Discovered {location}.")
        _save(state)


def reset_all() -> None:
    from database.storage import get_storage

    get_storage().purge_all()


def _save(state: GameState) -> None:
    try:
        from database.storage import get_storage

        get_storage().save_game(state)
    except Exception as exc:
        logger.warning("save skipped: %s", exc)
