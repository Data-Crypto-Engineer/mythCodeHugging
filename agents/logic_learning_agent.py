"""AGENT 5 — Logic & Learning. Brain: Groq.

Frames challenges, gives hints and writes the Python explanation. It may INVENT
new teaching metaphors — but it can never decide whether a solution is correct.
Verdicts come from `core.learning_engine.validate_puzzle`.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from models.game import GameState
from models.learning import ConceptReveal, LearningFrame, PuzzleHint
from agents.llm_factory import call_json, reasoner_llm
from core.learning_engine import concept_reveal, get_puzzle_prompt, static_hint
from utils.config import get_settings
from utils.logger import get_logger

logger = get_logger("learning")

ROLE = "Keeper of the Unwritten Journal"
GOAL = "Turn programming ideas into world mechanics, and reveal the real Python only after the player has felt the idea."
BACKSTORY = (
    "You teach by analogy. A guardian walking a room is a sequence; a door that decides is a condition; "
    "a river of identical tiles is a loop. You explain gently and never lecture."
)


def build_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role=ROLE, goal=GOAL, backstory=BACKSTORY, verbose=False, allow_delegation=False, llm=llm or reasoner_llm()
    )


def _frame_prompt(state: GameState, concept: str) -> str:
    prompt = get_puzzle_prompt(state.learning, concept)
    return (
        "Write a two-sentence narrative framing for a puzzle, so it feels like a world problem, not a lesson.\n"
        f"Concept (DO NOT NAME IT TO THE PLAYER YET): {concept}\n"
        f"Puzzle title: {prompt.title}\n"
        f"Puzzle kind: {concept} — the player interacts with structured controls, never raw code.\n"
        f"Player is in {state.world.current_location}.\n"
        "'intro' frames the problem; 'flavour' is one sensory sentence."
    )


def frame_challenge(state: GameState, concept: str | None = None) -> LearningFrame:
    concept = concept or state.learning.active_concept
    settings = get_settings()
    if settings.is_live:
        frame = call_json(reasoner_llm(settings), _frame_prompt(state, concept), LearningFrame, where="learning")
        if frame is not None:
            return frame
    return LearningFrame(
        concept=concept,
        intro=(
            "Elarion rarely explains itself. It simply builds a room, a door or a river — and waits to see "
            "whether you can give it the shape of a rule."
        ),
        flavour="Somewhere beneath the village, something is counting.",
    )


def _hint_prompt(state: GameState, concept: str, attempts: int) -> str:
    return (
        "Give a hint that helps without solving. The player has attempted this puzzle "
        f"{attempts} time(s).\n"
        f"Concept: {concept}. Location: {state.world.current_location}.\n"
        f"A safe factual seed you may paraphrase: {static_hint(concept, state.learning.next_difficulty)}\n"
        "'hint' is practical; 'nudge' is one encouraging sentence that names no programming term."
    )


def hint(state: GameState, concept: str | None = None) -> PuzzleHint:
    concept = concept or state.learning.active_concept
    attempts = state.learning.records.get(concept).attempts if concept in state.learning.records else 0
    settings = get_settings()
    if settings.is_live:
        result = call_json(reasoner_llm(settings), _hint_prompt(state, concept, attempts), PuzzleHint, where="learning")
        if result is not None:
            return result
    return PuzzleHint(
        hint=static_hint(concept, state.learning.next_difficulty),
        nudge="You are closer than you think. Change one thing at a time and watch what the world does.",
    )


def reveal(concept: str) -> ConceptReveal:
    """The Python reveal is DATA, not generation — it must always be accurate."""
    return concept_reveal(concept)
