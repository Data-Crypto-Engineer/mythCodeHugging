
"""AGENT 3 — Story Weaver.

Creates warm, age-appropriate fantasy scenes that respect:
- The Director's objective
- The current world and quest state
- Character memories
- The player's learning progression

AI-generated and offline scenes pass through the same sanitisation.
"""

from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.story import (
    DialogueLine,
    DirectorPlan,
    Scene,
    SceneAction,
)
from agents.llm_factory import call_json, weaver_llm
from core.learning_engine import concept_unlocked
from core.quest_manager import available_next
from core.state_manager import memory_brief
from utils.config import get_settings
from utils.logger import get_logger
from utils.validators import scrub_text


logger = get_logger("story")

ROLE = "Story Weaver of Elarion"
GOAL = (
    "Write vivid, warm, age-appropriate fantasy scenes "
    "that remember what the player has done."
)
BACKSTORY = (
    "You write for a bright ten-to-fourteen year old. "
    "Your prose is warm, concrete and a little strange. "
    "You never write anything graphic, and you always leave "
    "the player a meaningful choice."
)

MAX_ACTIONS = 5
MAX_DIALOGUE_LINES = 3

VALID_CONCEPTS = {
    "sequence",
    "conditions",
    "loops",
    "code_assembly",
}

VALID_ACTION_KINDS = {
    "explore",
    "talk",
    "travel",
    "build",
    "rest",
    "invent",
    "puzzle",
}


def build_agent(llm: Any | None = None) -> Agent:
    """Build the CrewAI Story Weaver agent."""
    return Agent(
        role=ROLE,
        goal=GOAL,
        backstory=BACKSTORY,
        verbose=False,
        allow_delegation=False,
        llm=llm or weaver_llm(),
    )


def _prompt(
    state: GameState,
    plan: DirectorPlan,
    action_label: str,
) -> str:
    """Build the scene-generation prompt from the current game state."""
    cast = ", ".join(
        memory_brief(state, npc_id)
        for npc_id in list(state.characters)[:3]
    )

    challenge = (
        plan.suggested_challenge
        if plan.suggested_challenge in VALID_CONCEPTS
        else "none"
    )

    puzzle_line = ""

    if challenge != "none":
        puzzle_line = (
            f"- Include exactly one action with kind='puzzle' "
            f"and concept='{challenge}'.\n"
            "- Frame the challenge as a natural problem in the world, "
            "not as a classroom lesson.\n"
        )

    destinations = available_next(state.quest.quest_id)

    return (
        "Write the next scene of a fantasy adventure.\n\n"
        f"DIRECTOR OBJECTIVE: "
        f"{scrub_text(plan.narrative_objective, 500)}\n"
        f"CATEGORY: {scrub_text(plan.event_category, 40)}\n"
        f"TENSION (1-5): {plan.dramatic_tension}\n"
        f"THE PLAYER JUST CHOSE: "
        f"{scrub_text(action_label, 240)}\n"
        f"LOCATION: {state.world.current_location} "
        f"in the kingdom of {state.world.kingdom}\n"
        f"QUEST: {state.quest.title} — {state.quest.objective}\n"
        f"WORLD: {state.world.as_context()}\n"
        f"CHARACTER MEMORY: {cast or 'No known character memories yet'}\n"
        f"RECENT EVENTS: "
        f"{' | '.join(state.recent_history[-3:]) or 'The story has just begun'}\n"
        f"POSSIBLE DESTINATIONS: "
        f"{', '.join(destinations) or 'None'}\n\n"
        "REQUIREMENTS:\n"
        "- Title: short and evocative, maximum 6 words.\n"
        "- Description: approximately 90-170 words, sensory, "
        "second person and age-appropriate.\n"
        "- Dialogue: 1-3 lines with speaker and text.\n"
        "- Actions: 2-4 meaningful choices.\n"
        "- Each action needs a unique snake_case action_id, "
        "a natural player-facing label, and a valid action kind.\n"
        f"{puzzle_line}"
        "- Consequence preview: one teasing sentence, "
        "without revealing the full outcome.\n"
        "- Characters: IDs of NPCs actually present "
        "(mira, nettle, sable, brack, elowen).\n"
        "- Category: echo the Director's category.\n"
        "- Do not invent completed quests, unlocked concepts, "
        "or mastered skills.\n"
        "- Do not contradict the supplied world state.\n"
        "- Do not repeat the same choice using different wording."
    )


def weave(
    state: GameState,
    plan: DirectorPlan,
    action_label: str,
) -> Scene:
    """Generate a scene, falling back to deterministic offline content."""
    settings = get_settings()

    if settings.is_live:
        try:
            scene = call_json(
                weaver_llm(settings),
                _prompt(state, plan, action_label),
                Scene,
                where="story",
            )

            if scene is not None:
                return _sanitise(scene, state, plan)

            logger.warning(
                "Story Weaver returned no usable scene; using offline scene."
            )

        except Exception:
            logger.exception(
                "Story generation failed; using offline scene."
            )

    return _sanitise(
        offline_scene(state, plan, action_label),
        state,
        plan,
    )


def _normalise_action(
    action: SceneAction,
    used_ids: set[str],
    index: int,
) -> SceneAction | None:
    """Clean an action and ensure its ID is unique."""
    label = scrub_text(action.label, 180)

    if not label:
        return None

    kind = action.kind

    if kind not in VALID_ACTION_KINDS:
        kind = "explore"

    action_id = scrub_text(action.action_id, 60).lower()

    # Keep action IDs predictable and safe for UI callbacks.
    cleaned_id = "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in action_id
    ).strip("_")

    if not cleaned_id:
        cleaned_id = f"choice_{index + 1}"

    if cleaned_id in used_ids:
        cleaned_id = f"{cleaned_id}_{index + 1}"

    used_ids.add(cleaned_id)

    concept = (
        action.concept
        if kind == "puzzle" and action.concept in VALID_CONCEPTS
        else ""
    )

    return SceneAction(
        action_id=cleaned_id,
        label=label,
        kind=kind,
        concept=concept,
    )


def _sanitise(
    scene: Scene,
    state: GameState,
    plan: DirectorPlan,
) -> Scene:
    """Normalise AI and offline scenes into the same safe structure."""
    scene.title = scrub_text(scene.title, 60) or f"Turn {state.turn}"

    scene.description = (
        scrub_text(scene.description, 1400)
        or "The world grows quiet around you. "
        "There is time to look around and choose your next step."
    )

    scene.dialogue = scene.dialogue[:MAX_DIALOGUE_LINES]

    clean_dialogue = []

    for line in scene.dialogue:
        speaker = scrub_text(line.speaker, 40) or "A Voice"
        text = scrub_text(line.text, 320)

        if text:
            clean_dialogue.append(
                DialogueLine(
                    speaker=speaker,
                    text=text,
                )
            )

    scene.dialogue = clean_dialogue

    scene.consequence_preview = (
        scrub_text(scene.consequence_preview, 200)
        or "Something in the world is waiting to unfold."
    )

    scene.location = (
        scrub_text(scene.location, 80)
        or state.world.current_location
    )

    # The Director's category is authoritative.
    if scene.category not in {
        "exploration",
        "dialogue",
        "puzzle",
        "discovery",
        "consequence",
        "transition",
    }:
        scene.category = "exploration"
    else:
        scene.category = plan.event_category

    # Only keep characters that exist in the current game.
    scene.characters = [
        npc_id
        for npc_id in scene.characters
        if npc_id in state.characters
    ][:5]

    used_ids: set[str] = set()
    actions: list[SceneAction] = []

    challenge = plan.suggested_challenge

    valid_challenge = (
        challenge in VALID_CONCEPTS
        and concept_unlocked(state.learning, challenge)
    )

    # Keep ordinary actions, but handle puzzle actions separately.
    # The planned challenge must have exactly one matching puzzle action.
    for index, action in enumerate(scene.actions):
        if action.kind == "puzzle":
            continue

        cleaned = _normalise_action(
            action,
            used_ids,
            index,
        )

        if cleaned is not None:
            actions.append(cleaned)

    if valid_challenge:
        puzzle_action = SceneAction(
            action_id=f"face_{challenge}",
            label="Step forward and face what the world is asking.",
            kind="puzzle",
            concept=challenge,
        )

        # Place the challenge first so it is easy to find.
        actions.insert(0, puzzle_action)
        used_ids.add(puzzle_action.action_id)

    # Ensure the player always has at least one choice.
    if not actions:
        actions.append(
            SceneAction(
                action_id="look_around",
                label="Look around and listen carefully.",
                kind="explore",
            )
        )

    # Enforce unique IDs and the UI action limit.
    final_actions = []
    final_ids = set()

    for action in actions:
        if action.action_id in final_ids:
            continue

        final_ids.add(action.action_id)
        final_actions.append(action)

        if len(final_actions) >= MAX_ACTIONS:
            break

    scene.actions = final_actions

    return scene


def offline_scene(
    state: GameState,
    plan: DirectorPlan,
    action_label: str,
) -> Scene:
    """Create a deterministic scene when AI generation is unavailable."""
    location = (
        scrub_text(state.world.current_location, 80)
        or "your current location"
    )

    mood = {
        "puzzle": (
            "The air goes quiet, the way a room does "
            "when it is about to ask you a question."
        ),
        "dialogue": (
            "Someone nearby seems to be waiting "
            "for the right moment to speak."
        ),
        "exploration": (
            "The path curves, and the village makes "
            "a sound you have not heard before."
        ),
        "discovery": (
            "Beneath the ordinary, something older "
            "is beginning to reveal itself."
        ),
        "consequence": (
            "A choice from earlier in your journey "
            "has begun to show its consequences."
        ),
        "transition": (
            "The familiar surroundings slowly give way "
            "to something new."
        ),
    }.get(
        plan.event_category,
        "The world shifts, patient and enormous.",
    )

    objective = scrub_text(
        plan.narrative_objective,
        240,
    ).strip()

    if objective:
        objective_sentence = (
            f"The purpose of this moment is simple: {objective.rstrip('.')}."
        )
    else:
        objective_sentence = (
            "There is still much to discover."
        )

    description = (
        f"{mood} You are in {location}. "
        f"{objective_sentence} "
        f"The kingdom keeps a careful record of what you do. "
        f"The water supply is {state.world.water_supply}, "
        f"the clockwork guardian is {state.world.clockwork_guardian}, "
        f"and the village's morale is "
        f"{state.world.village_morale} out of a hundred. "
        f"You chose to {scrub_text(action_label, 160).lower()}. "
        "The kingdom answers, but not completely — it never does."
    )

    dialogue: list[DialogueLine] = []

    for npc_id in ("mira", "sable", "nettle"):
        memory = state.characters.get(npc_id)

        if memory and plan.event_category in {"dialogue", "puzzle"}:
            greeting = scrub_text(
                memory.greeting_placeholder(),
                320,
            )

            if greeting:
                dialogue.append(
                    DialogueLine(
                        speaker=scrub_text(memory.name, 40) or "A Voice",
                        text=greeting,
                    )
                )
                break

    actions: list[SceneAction] = []

    challenge = plan.suggested_challenge

    if (
        challenge in VALID_CONCEPTS
        and concept_unlocked(state.learning, challenge)
    ):
        actions.append(
            SceneAction(
                action_id=f"face_{challenge}",
                label="Step forward and face what the world is asking.",
                kind="puzzle",
                concept=challenge,
            )
        )

    elif state.quest.path == "":
        from core.quest_manager import opener_actions

        for opener in opener_actions(state.quest.quest_id)[:3]:
            actions.append(
                SceneAction(
                    action_id=opener["id"],
                    label=opener["label"],
                    kind=opener["kind"],
                )
            )

    actions.extend(
        [
            SceneAction(
                action_id="ask_around",
                label="Ask the people nearby what they have noticed.",
                kind="talk",
            ),
            SceneAction(
                action_id="walk_on",
                label="Keep moving and observe the world around me.",
                kind="explore",
            ),
        ]
    )

    return Scene(
        title=f"{plan.event_category.title()} at {location}",
        description=description,
        dialogue=dialogue,
        actions=actions[:MAX_ACTIONS],
        consequence_preview=(
            "Something you did earlier is still deciding what it thinks of you."
        ),
        characters=list(state.characters)[:2],
        category=plan.event_category,
        location=location,
    )
