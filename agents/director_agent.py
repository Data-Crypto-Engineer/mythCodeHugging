"""AGENT 1 — Director. Brain: Gemini.

Coordinates the experience and PROPOSES a structured transition. It never
mutates state; `core.state_validator` decides what may be applied.
"""
from __future__ import annotations

import random
from typing import Any

from crewai import Agent

from models.game import GameState
from models.learning import CONCEPT_ORDER
from models.story import DirectorPlan
from agents.llm_factory import call_json, director_llm
from core.learning_engine import concept_unlocked, static_hint
from utils.config import get_settings
from utils.logger import get_logger

logger = get_logger("director")

ROLE = "Director of the MythCode Experience"
GOAL = "Choose the single most engaging next beat, honouring the world, the player's history and their learning stage."
BACKSTORY = (
    "You are the unseen hand that keeps Elarion coherent. You never invent state and never overwrite "
    "the world; you select and justify. You prefer consequence over coincidence."
)


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE,
        goal=GOAL,
        backstory=BACKSTORY,
        verbose=False,
        allow_delegation=False,
        llm=llm or director_llm(),
    )


def _prompt(state: GameState, action_label: str, action_kind: str, context_block: str) -> str:
    from core.quest_manager import available_next

    settings = get_settings()
    unlocked = [c for c in CONCEPT_ORDER if concept_unlocked(state.learning, c)]
    return (
        "You are the Director of an adaptive fantasy adventure for learners aged roughly 10-14.\n"
        f"PLAYER ACTION: \"{action_label}\" (kind: {action_kind})\n"
        f"CONTEXT:\n{context_block}\n"
        f"Available learning mechanics (unlocked so far): {', '.join(unlocked) or 'sequence'}\n"
        f"Next concept in the ladder: {state.learning.active_concept}\n"
        f"Possible quest destinations: {', '.join(available_next(state.quest.quest_id)) or 'none'}\n\n"
        "Decide the NEXT single beat. Constraints:\n"
        "- 'event_category' is one of: exploration, dialogue, puzzle, discovery, consequence, transition.\n"
        "- 'suggested_challenge' is 'none' or the NEXT concept only if the player is ready; never skip ahead.\n"
        "- 'proposed_changes' must use only these keys: water_supply (damaged|redirected|restored), "
        "forest_spirit_trust (int -100..100), clockwork_guardian (inactive|stirring|active|awakened), "
        "village_morale (int 0..100), energy_reserve (int 0..100), current_location (already discovered only).\n"
        "- Propose at most 2 changes, and only when the action justifies them.\n"
        "- Introduce controlled surprise, never arbitrary randomness.\n"
        f"- If a puzzle is chosen, its category is '{state.learning.active_concept}'. "
        f"A useful hint seed: {static_hint(state.learning.active_concept, state.learning.next_difficulty)}\n"
        "- 'required_agents' lists which specialists should contribute, e.g. [\"story\", \"world\"].\n"
        f"- Keep 'rationale' to one or two sentences. Story seed for reproducibility: {settings.story_seed}."
    )


def plan_turn(state: GameState, action_label: str, action_kind: str, context_block: str) -> DirectorPlan:
    """Return a validated DirectorPlan, falling back to a deterministic plan."""
    settings = get_settings()
    if settings.is_live:
        plan = call_json(director_llm(settings), _prompt(state, action_label, action_kind, context_block), DirectorPlan, where="director")
        if plan is not None:
            return _sanitise(plan, state)
        logger.warning("Director fell back to deterministic planning.")
    return offline_plan(state, action_label, action_kind)


def _sanitise(plan: DirectorPlan, state: GameState) -> DirectorPlan:
    from models.story import EVENT_CATEGORIES

    if plan.event_category not in EVENT_CATEGORIES:
        plan.event_category = "exploration"
    if plan.suggested_challenge != "none" and not concept_unlocked(state.learning, plan.suggested_challenge):
        plan.suggested_challenge = "none"
    plan.proposed_changes = plan.proposed_changes[:2]
    plan.dramatic_tension = max(1, min(5, int(plan.dramatic_tension or 1)))
    return plan


def offline_plan(state: GameState, action_label: str, action_kind: str) -> DirectorPlan:
    """Deterministic director used when no API keys are present (and in tests).

    Seeded so that identical input reproduces identical output.
    """
    rng = random.Random(f"{state.story_seed}:{state.session_id}:{state.turn}:{action_kind}")
    ready = state.learning.next_difficulty
    record = state.learning.records.get(state.learning.active_concept)
    concept_untried = record is None or record.successes < 1

    if action_kind == "puzzle" and concept_untried:
        category, challenge = "puzzle", state.learning.active_concept
    elif action_kind in {"talk", "rest"}:
        category, challenge = "dialogue", "none"
    elif state.turn > 0 and state.turn % 4 == 0 and concept_untried:
        category, challenge = "puzzle", state.learning.active_concept
    elif state.world.village_morale < 45:
        category, challenge = "consequence", "none"
    else:
        category = rng.choice(["exploration", "discovery", "dialogue"])
        challenge = "none"

    objective = {
        "puzzle": f"Teach the world the meaning of {state.learning.active_concept}.",
        "dialogue": "Let someone in Elarion reveal what they are afraid of.",
        "exploration": f"Let the player learn something true about {state.world.current_location}.",
        "discovery": "Reveal a piece of Elarion that reframes the water problem.",
        "consequence": "Show the cost of a choice already made.",
    }.get(category, "Advance the story of the silent water.")

    return DirectorPlan(
        rationale=f"Deterministic planning: the player chose '{action_label}', so the world answers with {category}.",
        narrative_objective=objective,
        event_category=category,
        suggested_challenge=challenge,
        required_agents=["story", "world"] + (["learning"] if challenge != "none" else []),
        proposed_changes=[],
        dramatic_tension=min(5, 1 + ready + (1 if state.world.village_morale < 50 else 0)),
    )
