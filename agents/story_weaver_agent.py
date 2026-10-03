"""AGENT 3 — Story Weaver. Brain: Groq.

Generates the scene. Must respect the Director's objective, world state and
character memories, and must always offer a PUZZLE action when a challenge is due.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.story import DirectorPlan, Scene, SceneAction
from agents.llm_factory import call_json, weaver_llm
from core.learning_engine import concept_unlocked
from core.quest_manager import available_next
from core.state_manager import memory_brief
from utils.config import get_settings
from utils.logger import get_logger
from utils.validators import scrub_text

logger = get_logger("story")

ROLE = "Story Weaver of Elarion"
GOAL = "Write vivid, warm, age-appropriate fantasy scenes that remember what the player has done."
BACKSTORY = (
    "You write for a bright ten-to-fourteen year old. Your prose is warm, concrete and a little strange. "
    "You never write anything graphic, and you always leave the player a real choice."
)

MAX_ACTIONS = 5


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE, goal=GOAL, backstory=BACKSTORY, verbose=False, allow_delegation=False, llm=llm or weaver_llm()
    )


def _prompt(state: GameState, plan: DirectorPlan, action_label: str) -> str:
    cast = ", ".join(
        memory_brief(state, npc_id) for npc_id in list(state.characters)[:3]
    )
    puzzle_line = ""
    if plan.suggested_challenge != "none":
        puzzle_line = (
            f"- You MUST include exactly one action with kind='puzzle' and concept='{plan.suggested_challenge}', "
            "framed as a natural world problem rather than a lesson.\n"
        )
    return (
        "Write the next scene of a fantasy adventure.\n"
        f"DIRECTOR OBJECTIVE: {plan.narrative_objective}\n"
        f"CATEGORY: {plan.event_category}\n"
        f"TENSION (1-5): {plan.dramatic_tension}\n"
        f"THE PLAYER JUST CHOSE: \"{action_label}\"\n"
        f"LOCATION: {state.world.current_location} in the kingdom of {state.world.kingdom}\n"
        f"QUEST: {state.quest.title} — {state.quest.objective}\n"
        f"WORLD: water={state.world.water_supply}, spirit_trust={state.world.forest_spirit_trust}, "
        f"guardian={state.world.clockwork_guardian}, morale={state.world.village_morale}\n"
        f"CHARACTER MEMORY: {cast}\n"
        f"RECENT EVENTS: {' | '.join(state.recent_history[-3:]) or 'the story has just begun'}\n"
        f"POSSIBLE DESTINATIONS: {', '.join(available_next(state.quest.quest_id)) or 'none'}\n\n"
        "Requirements:\n"
        "- 'title': short and evocative (max 6 words).\n"
        "- 'description': 90-170 words, sensory, second person, age-appropriate.\n"
        "- 'dialogue': 1-3 lines, each with 'speaker' and 'text'.\n"
        "- 'actions': 2-4 choices, each with 'action_id' (snake_case), 'label' (a full sentence the player would say), "
        "and 'kind' in explore|talk|travel|build|rest|invent|puzzle.\n"
        f"{puzzle_line}"
        "- 'consequence_preview': a single teasing sentence; never reveal the full outcome.\n"
        "- 'characters': ids of NPCs present (mira, nettle, sable, brack, elowen).\n"
        "- 'category': echo the director's category.\n"
        "Never state that the player mastered, learned or completed anything — only the game engine may do that."
    )


def weave(state: GameState, plan: DirectorPlan, action_label: str) -> Scene:
    settings = get_settings()
    if settings.is_live:
        scene = call_json(weaver_llm(settings), _prompt(state, plan, action_label), Scene, where="story")
        if scene is not None:
            return _sanitise(scene, state, plan)
        logger.warning("Story Weaver fell back to a templated scene.")
    return offline_scene(state, plan, action_label)


def _sanitise(scene: Scene, state: GameState, plan: DirectorPlan) -> Scene:
    scene.title = scrub_text(scene.title, 60) or f"Turn {state.turn}"
    scene.description = scrub_text(scene.description, 1400)
    scene.dialogue = scene.dialogue[:3]
    for line in scene.dialogue:
        line.speaker = scrub_text(line.speaker, 24) or "A Voice"
        line.text = scrub_text(line.text, 320)
    scene.consequence_preview = scrub_text(scene.consequence_preview, 200)
    scene.location = scene.location or state.world.current_location
    scene.category = plan.event_category

    actions = [action for action in scene.actions if action.label][:MAX_ACTIONS]
    has_puzzle = any(action.kind == "puzzle" for action in actions)
    if plan.suggested_challenge != "none" and not has_puzzle and concept_unlocked(state.learning, plan.suggested_challenge):
        actions.insert(
            0,
            SceneAction(
                action_id=f"face_{plan.suggested_challenge}",
                label="Face the challenge the world is offering me",
                kind="puzzle",
                concept=plan.suggested_challenge,
            ),
        )
    if not actions:
        actions = [SceneAction(action_id="look_around", label="Look around and listen", kind="explore")]
    scene.actions = actions[:MAX_ACTIONS]
    return scene


def offline_scene(state: GameState, plan: DirectorPlan, action_label: str) -> Scene:
    """Templated, deterministic scene — used in offline mode and in tests."""
    location = state.world.current_location
    mood = {
        "puzzle": "The air goes quiet, the way a room does when it is about to ask you a question.",
        "dialogue": "Someone has been waiting to say a thing they have not said yet.",
        "exploration": "The path curves, and the village makes a sound you have not heard before.",
        "discovery": "Under the ordinary, something older is showing an edge of itself.",
        "consequence": "What you chose earlier has arrived, and it is standing in front of you.",
    }.get(plan.event_category, "The world shifts, patient and enormous.")

    description = (
        f"{mood} You are still in {location}, and {plan.narrative_objective.lower()} "
        f"Elarion keeps a careful record of what you do: the water runs {state.world.water_supply}, "
        f"the guardian sleeps {state.world.clockwork_guardian}, and the village's heart sits at "
        f"{state.world.village_morale} out of a hundred. You chose to {action_label.lower()}. "
        "The kingdom answers, but not completely — it never does."
    )

    dialogue = []
    for npc_id in ("mira", "sable", "nettle"):
        memory = state.characters.get(npc_id)
        if memory and plan.event_category in {"dialogue", "puzzle"}:
            dialogue.append({"speaker": memory.name, "text": memory.greeting_placeholder()})
            break

    actions = []
    if plan.suggested_challenge != "none" and concept_unlocked(state.learning, plan.suggested_challenge):
        actions.append(
            SceneAction(
                action_id=f"face_{plan.suggested_challenge}",
                label="Step forward and face what the world is asking",
                kind="puzzle",
                concept=plan.suggested_challenge,
            )
        )
    elif state.quest.path == "":
        from core.quest_manager import opener_actions

        for opener in opener_actions(state.quest.quest_id)[:3]:
            actions.append(SceneAction(action_id=opener["id"], label=opener["label"], kind=opener["kind"]))

    actions.append(SceneAction(action_id="ask_around", label="Ask the people nearby what they have noticed", kind="talk"))
    actions.append(SceneAction(action_id="walk_on", label="Keep moving and watch the river", kind="explore"))

    return Scene(
        title=f"{plan.event_category.title()} at {location}",
        description=description,
        dialogue=[__import__("models.story", fromlist=["DialogueLine"]).DialogueLine(**line) for line in dialogue],
        actions=actions[:MAX_ACTIONS],
        consequence_preview="Something you did earlier is still deciding what it thinks of you.",
        characters=list(state.characters)[:2],
        category=plan.event_category,
        location=location,
    )
