"""World state + proposed mutations.

The World Keeper PROPOSES; the application VALIDATES and applies.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

WATER_STATES = {"damaged", "redirected", "restored", "unknown"}
GUARDIAN_STATES = {"inactive", "stirring", "active", "awakened"}


class ProposedChange(BaseModel):
    key: str
    new_value: str
    reason: str = ""


class MemoryNote(BaseModel):
    npc_id: str
    note: str


class WorldPatch(BaseModel):
    """Structured output of the World Keeper Agent."""
    changes: list[ProposedChange] = Field(default_factory=list)
    memory_notes: list[MemoryNote] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    continuity_note: str = ""


class WorldState(BaseModel):
    kingdom: str = "Elarion"
    current_location: str = "Whispering Village"
    water_supply: str = "damaged"
    forest_spirit_trust: int = 0            # -100..100
    clockwork_guardian: str = "inactive"
    village_morale: int = 60                # 0..100
    energy_reserve: int = 50                # 0..100
    discovered_locations: list[str] = Field(default_factory=lambda: ["Whispering Village"])
    completed_quests: list[str] = Field(default_factory=list)
    important_choices: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    npc_states: dict[str, str] = Field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        """Compact, prompt-safe snapshot."""
        return {
            "kingdom": self.kingdom,
            "location": self.current_location,
            "water_supply": self.water_supply,
            "spirit_trust": self.forest_spirit_trust,
            "guardian": self.clockwork_guardian,
            "morale": self.village_morale,
            "energy": self.energy_reserve,
            "discovered": self.discovered_locations,
            "completed": self.completed_quests,
            "conflicts": self.unresolved_conflicts[-4:],
        }
