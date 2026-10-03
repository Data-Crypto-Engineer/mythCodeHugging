from __future__ import annotations

from pydantic import BaseModel, Field

MAX_NPC_MEMORIES = 12


class NPCProfile(BaseModel):
    npc_id: str
    name: str
    role: str = ""
    traits: list[str] = Field(default_factory=list)
    voice: str = ""
    greeting: str = ""


class CharacterMemory(BaseModel):
    npc_id: str
    name: str
    role: str = ""
    disposition: int = 0                 # -100..100
    memories: list[str] = Field(default_factory=list)
    last_seen_turn: int = 0

    def remember(self, note: str) -> None:
        note = (note or "").strip()
        if not note or note in self.memories:
            return
        self.memories.append(note)
        if len(self.memories) > MAX_NPC_MEMORIES:
            # Keep the newest; the oldest are periodically folded into long-term memory.
            self.memories = self.memories[-MAX_NPC_MEMORIES:]
