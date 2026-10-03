"""Deterministic programming-challenge engine.

AI may FRAME, HINT and EXPLAIN. It may NEVER decide whether a solution is
correct — every verdict below is computed by simulation. No eval/exec anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.learning import (
    CONCEPT_ORDER,
    ConceptReveal,
    Invention,
    InventionBlock,
    LearningProgress,
    PuzzlePrompt,
    PuzzleResult,
)

_PUZZLE_FILE = Path(__file__).resolve().parent.parent / "data" / "puzzles.json"

_DIRECTION = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
_TURN_RIGHT = {"N": "E", "E": "S", "S": "W", "W": "N"}
_TURN_LEFT = {"N": "W", "W": "S", "S": "E", "E": "N"}
LEGAL_OPS = {"forward", "turn_left", "turn_right"}
MAX_SCRIPT_OPS = 20


def load_puzzles() -> dict[str, Any]:
    with _PUZZLE_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ── the deterministic interpreter (shared by all puzzle types) ────
def simulate_sequence(grid: dict[str, Any], ops: list[str]) -> dict[str, Any]:
    """Walk a guardian across a grid. Pure function; no side effects."""
    x = int(grid["start"]["x"])
    y = int(grid["start"]["y"])
    facing = str(grid["start"]["dir"])
    walls = {tuple(wall) for wall in grid.get("walls", [])}
    width, height = int(grid["w"]), int(grid["h"])
    path: list[list[int]] = [[x, y]]
    bumped = 0

    for op in ops:
        if op == "forward":
            dx, dy = _DIRECTION[facing]
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in walls:
                x, y = nx, ny
            else:
                bumped += 1
        elif op == "turn_right":
            facing = _TURN_RIGHT[facing]
        elif op == "turn_left":
            facing = _TURN_LEFT[facing]
        path.append([x, y])

    goal = [int(grid["goal"][0]), int(grid["goal"][1])]
    return {
        "path": path,
        "position": [x, y],
        "facing": facing,
        "reached": [x, y] == goal,
        "bumped": bumped,
        "grid": grid,
    }


def _condition_holds(expression: str, scenario: dict[str, bool]) -> bool:
    """Tiny whitelisted boolean interpreter. Deliberately NOT eval()."""
    expr = (expression or "").strip().lower()
    if not expr:
        return False
    if " and " in expr:
        return all(_condition_holds(part, scenario) for part in expr.split(" and "))
    if " or " in expr:
        return any(_condition_holds(part, scenario) for part in expr.split(" or "))
    if expr.startswith("not "):
        return not _condition_holds(expr[4:], scenario)
    return bool(scenario.get(expr, False))


def evaluate_rule(rule: dict[str, Any], scenario: dict[str, bool]) -> str:
    """Run one player-authored rule against one situation."""
    if _condition_holds(str(rule.get("condition", "")), scenario):
        return str(rule.get("then", "wait"))
    return str(rule.get("else", "wait"))


def expand_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    """Turn player blocks into a flat op list (a loop is just expansion)."""
    ops: list[str] = []
    for block in blocks:
        op = str(block.get("op", "")).strip()
        times = int(block.get("times", 1) or 1)
        times = max(0, min(times, MAX_SCRIPT_OPS))
        if op == "repeat":
            inner = str(block.get("inner", "forward"))
            if inner in LEGAL_OPS:
                ops.extend([inner] * times)
        elif op in LEGAL_OPS:
            ops.extend([op] * times)
    return ops[:MAX_SCRIPT_OPS]


# ── public API ────────────────────────────────────────────────────
def concept_unlocked(learning: LearningProgress, concept: str) -> bool:
    """Strict staged progression: a concept opens only after the previous one is solved."""
    index = CONCEPT_ORDER.index(concept)
    for previous in CONCEPT_ORDER[:index]:
        record = learning.records.get(previous)
        if not record or record.successes < 1:
            return False
    return True


def next_concept(learning: LearningProgress) -> str:
    for concept in CONCEPT_ORDER:
        record = learning.records.get(concept)
        if not record or record.successes < 1:
            return concept
    return CONCEPT_ORDER[-1]


def get_puzzle_prompt(learning: LearningProgress, concept: str | None = None) -> PuzzlePrompt:
    data = load_puzzles()
    concept = concept or next_concept(learning)
    pack = data[concept]
    variant = _pick_variant(pack["variants"], learning.next_difficulty)
    return PuzzlePrompt(
        puzzle_id=f"{concept}-d{variant['difficulty']}",
        concept=concept,
        title=pack["title"],
        instructions=pack["instructions"],
        difficulty=int(variant["difficulty"]),
        spec=variant,
        max_ops=int(variant.get("max_ops", MAX_SCRIPT_OPS)),
        max_blocks=int(variant.get("max_blocks", 3)),
    )


def _pick_variant(variants: list[dict[str, Any]], difficulty: int) -> dict[str, Any]:
    ordered = sorted(variants, key=lambda item: int(item.get("difficulty", 1)))
    index = max(0, min(len(ordered) - 1, int(difficulty) - 1))
    return ordered[index]


def validate_puzzle(concept: str, spec: dict[str, Any], submission: dict[str, Any]) -> PuzzleResult:
    """THE authority on correctness. Deterministic, side-effect free, unit-tested."""
    if concept == "sequence":
        return _validate_sequence(spec, submission)
    if concept == "loops":
        return _validate_loops(spec, submission)
    if concept == "conditions":
        return _validate_conditions(spec, submission)
    if concept == "code_assembly":
        return _validate_assembly(spec, submission)
    return PuzzleResult(concept=concept, solved=False, reason=f"Unknown challenge '{concept}'.")


def _validate_sequence(spec: dict[str, Any], submission: dict[str, Any]) -> PuzzleResult:
    ops = [str(op) for op in submission.get("ops", []) if str(op) in LEGAL_OPS]
    if not ops:
        return PuzzleResult(concept="sequence", solved=False, reason="The guardian received no commands.")
    if len(ops) > int(spec.get("max_ops", MAX_SCRIPT_OPS)):
        return PuzzleResult(
            concept="sequence",
            solved=False,
            reason=f"That is {len(ops)} commands; the scroll holds only {spec.get('max_ops')}.",
        )
    trace = simulate_sequence(spec["grid"], ops)
    if not trace["reached"]:
        return PuzzleResult(
            concept="sequence",
            solved=False,
            reason=f"The guardian stopped at {trace['position']} and never reached the goal.",
            trace=trace,
        )
    return PuzzleResult(
        concept="sequence",
        solved=True,
        reason="The guardian reached the far tile.",
        score=1.0 if trace["bumped"] == 0 else 0.8,
        trace=trace,
    )


def _validate_loops(spec: dict[str, Any], submission: dict[str, Any]) -> PuzzleResult:
    blocks = list(submission.get("blocks", []))
    if not blocks:
        return PuzzleResult(concept="loops", solved=False, reason="No blocks were placed on the river.")
    if len(blocks) > int(spec.get("max_blocks", 3)):
        return PuzzleResult(
            concept="loops",
            solved=False,
            reason="Too many blocks — the whole point is to repeat instead of repeating yourself.",
        )
    ops = expand_blocks(blocks)
    steps = int(spec.get("steps", 0))
    grid = {
        "w": steps + 1,
        "h": 1,
        "walls": [],
        "start": {"x": 0, "y": 0, "dir": "E"},
        "goal": [steps, 0],
    }
    trace = simulate_sequence(grid, ops)
    if trace["reached"]:
        return PuzzleResult(
            concept="loops", solved=True, reason="The guardian crossed the hollow river.", score=1.0, trace=trace
        )
    return PuzzleResult(
        concept="loops",
        solved=False,
        reason=f"The guardian is at tile {trace['position'][0]} of {steps}.",
        trace=trace,
    )


def _validate_conditions(spec: dict[str, Any], submission: dict[str, Any]) -> PuzzleResult:
    rule = {
        "condition": str(submission.get("condition", "")),
        "then": str(submission.get("then", "wait")),
        "else": str(submission.get("else", "wait")),
    }
    outcomes = []
    for scenario in spec.get("scenarios", []):
        facts = dict(scenario.get("facts", {}))
        expected = str(scenario.get("expect", "wait"))
        got = evaluate_rule(rule, facts)
        outcomes.append({"facts": facts, "expected": expected, "got": got, "ok": got == expected})
    failures = [item for item in outcomes if not item["ok"]]
    if failures:
        first = failures[0]
        return PuzzleResult(
            concept="conditions",
            solved=False,
            reason=(
                "The door-keeper fails in one situation: "
                f"with {first['facts']} it should {first['expected']} but your rule says {first['got']}."
            ),
            trace={"outcomes": outcomes},
        )
    return PuzzleResult(
        concept="conditions",
        solved=True,
        reason="Your rule holds in every situation the door-keeper knows.",
        score=1.0,
        trace={"outcomes": outcomes},
    )


def _validate_assembly(spec: dict[str, Any], submission: dict[str, Any]) -> PuzzleResult:
    chosen = [str(line) for line in submission.get("lines", [])]
    solution = [str(line) for line in spec.get("solution", [])]
    if chosen == solution:
        return PuzzleResult(
            concept="code_assembly", solved=True, reason="The scroll is restored.", score=1.0,
            trace={"lines": chosen},
        )
    correct = sum(1 for a, b in zip(chosen, solution) if a == b)
    return PuzzleResult(
        concept="code_assembly",
        solved=False,
        reason=f"{correct} of {len(solution)} lines sit in the right place.",
        trace={"lines": chosen},
    )


def record_attempt(
    learning: LearningProgress,
    concept: str,
    result: PuzzleResult,
    hints_used: int = 0,
    difficulty: int = 1,
) -> LearningProgress:
    """Write learning progress from an OBJECTIVE outcome. Never from narration."""
    record = learning.record(concept)
    record.introduced = True
    record.attempts += 1
    record.hints_used += max(0, hints_used)
    record.difficulty = difficulty
    if result.solved:
        record.successes += 1
        if record.attempts == 1:
            record.first_try_successes += 1
        record.revealed = True
        if concept not in learning.revealed:
            learning.revealed.append(concept)
    # advance the stage only when the current concept is demonstrably understood
    if concept_unlocked(learning, "conditions"):
        learning.stage = 1
    if concept_unlocked(learning, "loops"):
        learning.stage = 2
    if concept_unlocked(learning, "code_assembly"):
        learning.stage = 3
    learning.active_concept = next_concept(learning)
    return learning


def concept_reveal(concept: str) -> ConceptReveal:
    """The Python reveal is taken from data, never invented by a model."""
    pack = load_puzzles()[concept]
    return ConceptReveal(**pack["reveal"])


def static_hint(concept: str, difficulty: int = 1) -> str:
    pack = load_puzzles()[concept]
    variant = _pick_variant(pack["variants"], difficulty)
    return str(variant.get("hint", "")) or "Read the world carefully; the rule is hidden in what repeats."


def describe_program(concept: str, submission: dict[str, Any]) -> str:
    """Human-readable recap of what the player built (used in journals)."""
    if concept == "sequence":
        return " → ".join(str(op).replace("_", " ") for op in submission.get("ops", [])) or "(empty scroll)"
    if concept == "loops":
        parts = []
        for block in submission.get("blocks", []):
            if str(block.get("op")) == "repeat":
                parts.append(f"repeat {block.get('inner')} x{block.get('times')}")
            else:
                parts.append(f"{block.get('op')} x{block.get('times')}")
        return " → ".join(parts) or "(empty scroll)"
    if concept == "conditions":
        return f"if {submission.get('condition')} then {submission.get('then')} else {submission.get('else')}"
    if concept == "code_assembly":
        return " · ".join(str(line) for line in submission.get("lines", []))
    return ""


def compose_invention(name: str, blocks: list[dict[str, Any]], turn: int) -> Invention:
    """Player-created magical invention: deterministic, safe, describable."""
    parsed = [InventionBlock(**block) for block in blocks][:6]
    effect_bits = []
    for block in parsed:
        if block.kind == "repeat":
            effect_bits.append(f"repeats {block.inner or 'action'} ×{block.times}")
        elif block.kind == "if":
            effect_bits.append(f"decides when {block.condition or 'a condition holds'}")
        elif block.kind == "glow":
            effect_bits.append("sheds steady light")
        else:
            effect_bits.append(block.kind.replace("_", " "))
    effect = "This device " + ", ".join(effect_bits[:4]) + "." if effect_bits else "The device hums, unfinished."
    return Invention(name=(name.strip()[:48] or "Unnamed Device"), blocks=parsed, effect=effect, created_turn=turn)
