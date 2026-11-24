
"""AGENT 6 — Continuity and Safety Warden.

Reviews generated scenes for child-appropriate content, continuity and
consistency with the Director's plan.

Deterministic checks always run, including when the app is offline.
AI review is an additional layer, never the final authority.
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
from utils.validators import is_child_safe, scrub_text


logger = get_logger("safety")

ROLE = "Continuity and Safety Warden"
GOAL = (
    "Catch continuity breaks, impossible state changes and content "
    "unsuitable for a young player."
)
BACKSTORY = (
    "You are the quiet editor who reads everything twice. "
    "When in doubt you object, because a broken world teaches nothing."
)

ALLOWED_ACTION_KINDS = {
    "explore",
    "talk",
    "puzzle",
    "travel",
    "build",
    "rest",
    "invent",
}

PROGRESS_CLAIMS = (
    "you have mastered",
    "you have learned",
    "quest completed",
    "you have unlocked",
)


def build_agent(llm: Any | None = None) -> Agent:
    """Build the CrewAI safety agent."""
    return Agent(
        role=ROLE,
        goal=GOAL,
        backstory=BACKSTORY,
        verbose=False,
        allow_delegation=False,
        llm=llm or reasoner_llm(),
    )


def _scene_text(scene: Scene) -> str:
    """Collect all player-facing text for deterministic safety checks."""
    parts = [
        scene.title,
        scene.description,
        scene.consequence_preview,
    ]

    parts.extend(
        f"{line.speaker}: {line.text}"
        for line in scene.dialogue
    )

    parts.extend(
        action.label
        for action in scene.actions
    )

    return " ".join(parts)


def local_review(
    state: GameState,
    scene: Scene | None,
    changes: list[ProposedChange],
    plan: DirectorPlan | None,
) -> SafetyVerdict:
    """Run deterministic checks without relying on an AI provider."""
    issues: list[str] = []
    requires_retry = False

    if scene is not None:
        # Required player-facing content.
        if not scrub_text(scene.title, 100):
            issues.append("Scene title is empty.")
            requires_retry = True

        if not scrub_text(scene.description, 1800):
            issues.append("Scene description is empty.")
            requires_retry = True

        # Child-safety filter.
        if not is_child_safe(_scene_text(scene)):
            issues.append("Scene text tripped the content filter.")
            requires_retry = True

        # The player must always have at least one meaningful choice.
        if not scene.actions:
            issues.append("Scene offered the player no choices.")
            requires_retry = True

        # Action IDs must be present and unique.
        action_ids = [
            action.action_id.strip()
            for action in scene.actions
        ]

        if any(not action_id for action_id in action_ids):
            issues.append("Scene contains an action with an empty ID.")
            requires_retry = True

        if len(action_ids) != len(set(action_ids)):
            issues.append("Scene contains duplicate action IDs.")
            requires_retry = True

        # Reject malformed or unsupported action types.
        for action in scene.actions:
            if action.kind not in ALLOWED_ACTION_KINDS:
                issues.append(
                    f"Scene contains unsupported action kind '{action.kind}'."
                )
                requires_retry = True

            if not scrub_text(action.label, 240):
                issues.append("Scene contains an empty action label.")
                requires_retry = True

        # A planned programming challenge must actually be offered.
        if plan and plan.suggested_challenge != "none":
            matching_puzzles = [
                action
                for action in scene.actions
                if (
                    action.kind == "puzzle"
                    and action.concept == plan.suggested_challenge
                )
            ]

            if len(matching_puzzles) != 1:
                issues.append(
                    "The scene does not contain exactly one puzzle "
                    "for the planned programming concept."
                )
                requires_retry = True

        # Progress claims must come from verified game-engine results,
        # not generated narrative text.
        lowered = _scene_text(scene).lower()

        for phrase in PROGRESS_CLAIMS:
            if phrase in lowered:
                issues.append(
                    f"Scene claimed unverified progress ('{phrase}')."
                )
                requires_retry = True

    # Check important monotonic world-state rules.
    for change in changes or []:
        if change.key == "clockwork_guardian":
            order = [
                "inactive",
                "stirring",
                "active",
                "awakened",
            ]

            current = state.world.clockwork_guardian
            proposed = str(change.new_value)

            if (
                current in order
                and proposed in order
                and order.index(proposed) < order.index(current)
            ):
                issues.append(
                    "The clockwork guardian cannot move backwards."
                )

        if (
            change.key == "water_supply"
            and state.world.water_supply == "restored"
            and change.new_value != "restored"
        ):
            issues.append(
                "Restored water cannot be changed back to an earlier state."
            )

    return SafetyVerdict(
        approved=not issues,
        issues=issues,
        corrections=[],
        requires_retry=requires_retry,
    )


def _ai_prompt(
    state: GameState,
    scene: Scene,
    changes: list[ProposedChange],
    plan: DirectorPlan | None,
) -> str:
    """Build a bounded prompt for the optional AI review."""
    return (
        "Review this game turn for a player aged about 10-14.\n\n"
        f"WORLD: {state.world.as_context()}\n"
        f"DIRECTOR OBJECTIVE: "
        f"{plan.narrative_objective if plan else 'Not specified'}\n"
        f"PLANNED CHALLENGE: "
        f"{plan.suggested_challenge if plan else 'none'}\n\n"
        f"SCENE TITLE: {scene.title}\n"
        f"SCENE DESCRIPTION: {scene.description}\n"
        f"DIALOGUE: "
        f"{[(line.speaker, line.text) for line in scene.dialogue]}\n"
        f"ACTIONS: "
        f"{[(a.action_id, a.label, a.kind, a.concept) for a in scene.actions]}\n"
        f"PROPOSED CHANGES: "
        f"{[(c.key, c.new_value) for c in changes]}\n\n"
        "Object if the scene is unsuitable for a young player, "
        "contradicts established world facts, claims unverified progress, "
        "or teaches/fragments the wrong programming concept. "
        "Do not invent facts about the game state. "
        "Return a SafetyVerdict with concrete issues. "
        "Set requires_retry true only when regenerating the scene "
        "could reasonably fix the problem."
    )


def review(
    state: GameState,
    scene: Scene | None,
    changes: list[ProposedChange],
    plan: DirectorPlan | None = None,
) -> SafetyVerdict:
    """Run local checks first, then optional AI review.

    AI review can add objections but cannot override a deterministic veto.
    If the AI provider fails, the local verdict is still returned.
    """
    verdict = local_review(
        state=state,
        scene=scene,
        changes=changes,
        plan=plan,
    )

    # A deterministic retry-worthy issue already blocks this scene.
    if not verdict.approved and verdict.requires_retry:
        return verdict

    if scene is None:
        return verdict

    try:
        settings = get_settings()

        if not settings.is_live:
            return verdict

        ai_verdict = call_json(
            reasoner_llm(settings),
            _ai_prompt(state, scene, changes, plan),
            SafetyVerdict,
            retries=1,
            where="safety",
        )

        if ai_verdict is None:
            return verdict

        combined_issues = sorted(
            set(verdict.issues) | set(ai_verdict.issues)
        )

        # A positive AI response must never erase a local objection.
        approved = verdict.approved and ai_verdict.approved

        return SafetyVerdict(
            approved=approved,
            issues=combined_issues,
            corrections=[
                scrub_text(item, 300)
                for item in ai_verdict.corrections
                if scrub_text(item, 300)
            ][:5],
            requires_retry=(
                verdict.requires_retry
                or (
                    ai_verdict.requires_retry
                    and verdict.approved
                    and not ai_verdict.approved
                )
            ),
        )

    except Exception:
        # Safety review must remain available when an optional AI service
        # is unavailable. The deterministic result is retained.
        logger.exception(
            "Optional AI safety review failed; keeping local verdict."
        )
        return verdict


def safe_scene(state: GameState) -> Scene:
    """Create a neutral fallback scene using the actual current world state.

    Do not hardcode old story facts such as a sleeping guardian or damaged
    river: those details may no longer match the saved playthrough.
    """
    location = scrub_text(
        state.world.current_location,
        80,
    ) or "your current location"

    return Scene(
        title="A Moment to Gather Your Thoughts",
        description=(
            f"The world grows quiet for a moment in {location}. "
            "You have time to look around, notice what has changed, "
            "and decide what you would like to do next. "
            "There is no need to rush. The path is still yours to choose."
        ),
        dialogue=[],
        actions=[
            {
                "action_id": "look_again",
                "label": "Look around carefully before choosing.",
                "kind": "explore",
            },
            {
                "action_id": "walk_on",
                "label": "Continue exploring at my own pace.",
                "kind": "explore",
            },
        ],
        consequence_preview="Take a moment; the next step is yours.",
        characters=[],
        category="exploration",
        location=location,
    )
