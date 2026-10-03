"""Deterministic world-state validation. The last line of defence.

Guarantees (tested):
  * enum fields only hold legal values
  * numeric fields are clamped, never trusted
  * discoveries, completions and ledger entries are MONOTONIC (history is never lost)
  * current_location must be a discovered location
"""
from __future__ import annotations

from models.game import GameState
from models.world import (
    GUARDIAN_STATES,
    WATER_STATES,
    ProposedChange,
    WorldState,
)
from utils.validators import clamp_int, scrub_text

# key -> (kind, spec)
_NUMERIC_RULES: dict[str, tuple[int, int]] = {
    "village_morale": (0, 100),
    "forest_spirit_trust": (-100, 100),
    "energy_reserve": (0, 100),
}
_ENUM_RULES: dict[str, set[str]] = {
    "water_supply": WATER_STATES,
    "clockwork_guardian": GUARDIAN_STATES,
}
_MONOTONIC_LIST_KEYS = {"discovered_locations", "completed_quests", "important_choices"}
_SIMPLE_TEXT_KEYS = {"kingdom", "current_location"}


def validate_state(state: GameState) -> list[str]:
    """Repair in place and return human-readable problems found."""
    problems: list[str] = []
    world: WorldState = state.world

    for key, (low, high) in _NUMERIC_RULES.items():
        raw = getattr(world, key)
        fixed = clamp_int(raw, low, high, low)
        if fixed != raw:
            problems.append(f"{key} out of range ({raw}) -> clamped to {fixed}")
            setattr(world, key, fixed)

    for key, allowed in _ENUM_RULES.items():
        raw = str(getattr(world, key))
        if raw not in allowed:
            problems.append(f"{key} has illegal value '{raw}' -> 'unknown'")
            setattr(world, key, "unknown")

    # de-duplicate while preserving order (never drop, only dedupe)
    for key in _MONOTONIC_LIST_KEYS:
        values = list(dict.fromkeys(getattr(world, key)))
        if len(values) != len(getattr(world, key)):
            problems.append(f"{key} contained duplicates -> de-duplicated")
            setattr(world, key, values)

    if not world.discovered_locations:
        problems.append("discovered_locations was empty -> restored home village")
        world.discovered_locations = ["Whispering Village"]
    if world.current_location not in world.discovered_locations:
        problems.append(
            f"current_location '{world.current_location}' was undiscovered -> moved to the first known location"
        )
        world.current_location = world.discovered_locations[0]

    for npc_id, disposition in list((world.npc_states or {}).items()):
        _ = disposition, npc_id  # npc_states holds short descriptors, free-form by design

    if state.learning.active_concept not in {"sequence", "conditions", "loops", "code_assembly"}:
        problems.append("active_concept was invalid -> reset to 'sequence'")
        state.learning.active_concept = "sequence"

    return problems


def validate_changes(
    state: GameState, changes: list[ProposedChange]
) -> tuple[list[ProposedChange], list[str]]:
    """Filter an agent's proposed mutations. Returns (accepted, rejections).

    Nothing is applied here. This function decides what is ALLOWED to be applied.
    """
    accepted: list[ProposedChange] = []
    rejected: list[str] = []
    world = state.world

    for change in changes or []:
        key = scrub_text(change.key, 60).strip()
        if not key:
            rejected.append("empty change key")
            continue

        if key in _MONOTONIC_LIST_KEYS:
            rejected.append(f"{key} is append-only and cannot be overwritten by an agent")
            continue
        if key in ("kingdom", "completed_quests"):
            rejected.append(f"{key} is managed by the quest engine, not by agents")
            continue

        if key in _NUMERIC_RULES:
            low, high = _NUMERIC_RULES[key]
            value = clamp_int(change.new_value, low, high, getattr(world, key))
            accepted.append(ProposedChange(key=key, new_value=str(value), reason=change.reason))
            continue

        if key in _ENUM_RULES:
            value = scrub_text(change.new_value, 20).lower()
            if value not in _ENUM_RULES[key]:
                rejected.append(f"{key}='{value}' is not a legal state")
                continue
            if key == "water_supply" and world.water_supply == "restored" and value != "restored":
                rejected.append("restored water cannot be un-restored by a narrative change")
                continue
            if key == "clockwork_guardian":
                order = ["inactive", "stirring", "active", "awakened"]
                if order.index(value) < order.index(world.clockwork_guardian):
                    rejected.append("the guardian cannot be de-awakened")
                    continue
            accepted.append(ProposedChange(key=key, new_value=value, reason=change.reason))
            continue

        if key in _SIMPLE_TEXT_KEYS:
            value = scrub_text(change.new_value, 60)
            if not value:
                rejected.append(f"{key} cannot be blank")
                continue
            if key == "current_location" and value not in world.discovered_locations:
                rejected.append(f"cannot travel to undiscovered location '{value}'")
                continue
            accepted.append(ProposedChange(key=key, new_value=value, reason=change.reason))
            continue

        rejected.append(f"unknown state key '{key}'")

    return accepted, rejected


def apply_changes(state: GameState, changes: list[ProposedChange]) -> list[str]:
    """Apply already-validated changes. Returns applied descriptions."""
    applied: list[str] = []
    for change in changes:
        setattr(state.world, change.key, change.new_value)
        applied.append(f"{change.key} -> {change.new_value}")
    return applied
