"""AGENT 6 (mandatory) — Continuity & Safety. Brain: Groq.

Reviews agent output for continuity, world-rule consistency and age-appropriateness.
Python validators run ALWAYS and independently; if the AI review is unavailable we
still ship a safe turn.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.story import DirectorPlan, Scene, SafetyVerdict
from models.world import ProposedChange
from agents.llm_factory import call_json, reasoner_llm
from utils.config import get_settings
from utils.logger import get_logger
from utils.validators import is_child_safe

logger = get_logger("safety")

ROLE = "Continuity and Safety Warden"
GOAL = "Catch continuity breaks, impossible state changes and any content unsuitable for a young player."
BACKSTORY = (
    "You are the quiet editor who reads everything twice. When in doubt you object, "
    "because a broken world teaches nothing."
)


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE, goal=GOAL, backstory=BACKSTORY, verbose=False, allow_delegation=False, llm=llm or reasoner_llm()
   I'll deliver the rest of the project now, keeping it tight.

<artifact identifier="mythcode-intelligence" type="markdown" title="MythCode — Intelligence (core engine, 6 agents, CrewAI Flow)">
# MythCode — Artifact 2/3 · Intelligence (continued)

## 📄 `agents/continuity_safety_agent.py`

```python
"""AGENT 6 (mandatory) — Continuity & Safety. Brain: Groq.

Reviews agent output for continuity, world-rule consistency and age-appropriateness.
Python validators run ALWAYS and independently; if the AI review is unavailable we
still ship a safe turn.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.story import DirectorPlan, Scene, SafetyVerdict
from models.world import ProposedChange
from agents.llm_factory import call_json, reasoner_llm
from utils.config import get_settings
from utils.logger import get_logger
from utils.validators import is_child_safe

logger = get_logger("safety")

ROLE = "Continuity and Safety Warden"
GOAL = "Catch continuity breaks, impossible state changes and any content unsuitable for a young player."
BACKSTORY = (
    "You are the quiet editor who reads everything twice. When in doubt you object, "
    "because a broken world teaches nothing."
)


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE, goal=GOAL, backstory=BACKSTORY, verbose=False, allow_delegation=False, llm=llm or reasoner_llm()
    )


def local_review(state: GameState, scene: Scene | None, changes: list[ProposedChange], plan: DirectorPlan | None) -> SafetyVerdict:
    """Deterministic, always-on review. Runs even with zero API keys."""
    issues: list[str] = []

    if scene is not None:
        blob = " ".join(
            [scene.title, scene.description, scene.consequence_preview]
            + [f"{line.speaker}: {line.text}" for line in scene.dialogue]
            + [action.label for action in scene.actions]
        )
        if not is_child_safe(blob):
            issues.append("Scene text tripped the content filter.")
        if not scene.actions:
            issues.append("Scene offered the player no choices.")
        if plan and plan.suggested_challenge != "none":
            if not any(action.kind == "puzzle" for action in scene.actions):
                issues.append("A challenge was due but the scene offered none.")

    # Unsupported claims about progress must never reach the player.
    lowered = (scene.description if scene else "").lower()
    for phrase in ("you have mastered", "you have learned", "quest completed", "you have unlocked"):
        if phrase in lowered:
            issues.append(f"Scene claimed unverified progress ('{phrase}').")

    for change in changes:
        if change.key == "clockwork_guardian" and state.world.clockwork_guardian == "awakened":
            issues.append("Guardian cannot regress from awakened.")

    return SafetyVerdict(
        approved=not issues,
        issues=issues,
        corrections=[],
        requires_retry=bool([i for i in issues if "content filter" in i or "progress" in i]),
    )


def _ai_prompt(state: GameState, scene: Scene, changes: list[ProposedChange], plan: DirectorPlan | None) -> str:
    return (
        "Review this game turn for a player aged about 10-14.\n"
        f"WORLD: water={state.world.water_supply}, spirit_trust={state.world.forest_spirit_trust}, "
        f"guardian={state.world.clockwork_guardian}, morale={state.world.village_morale}\n"
        f"DIRECTOR OBJECTIVE: {plan.narrative_objective if plan else 'n/a'}\n"
        f"SCENE: {scene.title} — {scene.description}\n"
        f"DIALOGUE: {[(line.speaker, line.text) for line in scene.dialogue]}\n"
        f"PROPOSED CHANGES: {[(c.key, c.new_value) for c in changes]}\n\n"
        "Object if: content is graphic, frightening in a harmful way, or unsuitable for a child; "
        "a change contradicts the world; the scene claims progress the engine did not verify; "
        "or the learning framing describes the wrong programming idea. "
        "Set 'approved' false and list concrete 'issues'. Set 'requires_retry' true only if the "
        "problem is fixable by regenerating the scene."
    )


def review(state: GameState, scene: Scene | None, changes: list[ProposedChange], plan: DirectorPlan | None = None) -> SafetyVerdict:
    verdict = local_review(state, scene, changes, plan)
    if not verdict.approved and verdict.requires_retry:
        return verdict  # deterministic veto; no point spending an API call
    settings = get_settings()
    if settings.is_live and scene is not None:
        ai = call_json(reasoner_llm(settings), _ai_prompt(state, scene, changes, plan), SafetyVerdict, retries=1, where="safety")
        if ai is not None:
            merged = sorted(set(verdict.issues) | set(ai.issues))
            return SafetyVerdict(
                approved=verdict.approved and ai.approved,
                issues=merged,
                corrections=ai.corrections,
                requires_retry=ai.requires_retry and verdict.approved,
            )
    return verdict


SAFE_FALLBACK_SCENE = Scene(
    title="The Path Holds Its Breath",
    description=(
        "For a moment the world goes quiet around you, as though Elarion is setting something down "
        "gently. The river still runs wrong, the guardian still sleeps, and the village still waits. "
        "Nothing has been lost — you simply have another chance to choose."
    ),
    dialogue=[],
    actions=[
        {"action_id": "look_again", "label": "Look again at what is in front of you", "kind": "explore"},
        {"action_id": "walk_on", "label": "Follow the riverbank a little further", "kind": "explore"},
    ],
    consequence_preview="The world is patient with you.",
    characters=[],
    category="exploration",
    location="Whispering Village",
)


def safe_scene(state: GameState) -> Scene:
    """Predefined safe narrative response — used when generation fails twice."""
    scene = SAFE_FALLBACK_SCENE.model_copy(deep=True)
    scene.location = state.world.current_location
    return scene
