from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuestDefinition(BaseModel):
    id: str
    title: str
    objective: str
    location: str = ""
    concept_hint: str = "sequence"
    openers: list[dict[str, Any]] = Field(default_factory=list)
    next: dict[str, str] = Field(default_factory=dict)


class QuestProgress(BaseModel):
    quest_id: str
    title: str
    objective: str
    location: str = ""
    stage: int = 0
    status: str = "active"           # active | completed
    path: str = ""                   # the chosen branch id, e.g. "spirit"
    concept_hint: str = "sequence"
    flags: dict[str, Any] = Field(default_factory=dict)
