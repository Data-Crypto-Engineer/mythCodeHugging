from __future__ import annotations

from pydantic import BaseModel, Field

from models.world import ProposedChange

EVENT_CATEGORIES = {"exploration", "dialogue", "puzzle", "discovery", "consequence", "transition"}


class DialogueLine(BaseModel):
    speaker: str
    text: str


class SceneAction(BaseModel):
    action_id: str
    label: str
    kind: str = "explore"      # explore | talk | puzzle | travel | build | rest | invent
    concept: str = ""


class Scene(BaseModel):
    """Structured output of the Story Weaver Agent."""
    title: str
    description: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    actions: list[SceneAction] = Field(default_factory=list)
    consequence_preview: str = ""
    characters: list[str] = Field(default_factory=list)
    category: str = "exploration"
    location: str = ""


class DirectorPlan(BaseModel):
    """Structured output of the Director Agent. A PROPOSAL, never a mutation."""
    rationale: str = ""
    narrative_objective: str = ""
    event_category: str = "exploration"
    suggested_challenge: str = "none"      # sequence|conditions|loops|code_assembly|none
    required_agents: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    dramatic_tension: int = 1
    path_hint: str = ""


class SafetyVerdict(BaseModel):
    """Structured output of the Continuity & Safety Agent."""
    approved: bool = True
    issues: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    requires_retry: bool = False
