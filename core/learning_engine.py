
"""Deterministic programming-challenge engine.

AI may FRAME, HINT and EXPLAIN.
It may NEVER decide whether a solution is correct.

Every verdict is computed by deterministic Python simulation.
No eval() or exec() is used.
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

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

_PUZZLE_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "puzzles.json"
)

_DIRECTION = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}

_TURN_RIGHT = {
    "N": "E",
    "E": "S",
    "S": "W",
    "W": "N",
}

_TURN_LEFT = {
    "N": "W",
    "W": "S",
    "S": "E",
    "E": "N",
}

LEGAL_OPS = {
    "forward",
    "turn_left",
    "turn_right",
}

MAX_SCRIPT_OPS = 20
MAX_BLOCKS = 20
MAX_HINTS = 100

VALID_CONCEPTS = set(CONCEPT_ORDER)


# ---------------------------------------------------------------------
# Puzzle data
# ---------------------------------------------------------------------

def load_puzzles() -> dict[str, Any]:
    """Load the curated puzzle definitions.

    Raises a descriptive error if the puzzle data is missing or invalid.
    """

    if not _PUZZLE_FILE.exists():
        raise FileNotFoundError(
            f"Puzzle data file not found: {_PUZZLE_FILE}"
        )

    try:
        with _PUZZLE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Puzzle data contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Puzzle data must contain a JSON object."
        )

    missing = VALID_CONCEPTS - set(data.keys())

    if missing:
        raise ValueError(
            "Puzzle data is missing concepts: "
            + ", ".join(sorted(missing))
        )

    for concept in CONCEPT_ORDER:
        pack = data[concept]

        if not isinstance(pack, dict):
            raise ValueError(
                f"Puzzle definition for '{concept}' must be an object."
            )

        variants = pack.get("variants")

        if not isinstance(variants, list) or not variants:
            raise ValueError(
                f"Concept '{concept}' must contain at least one variant."
            )

    return data


# ---------------------------------------------------------------------
# Small validation helpers
# ---------------------------------------------------------------------

def _invalid(
    concept: str,
    reason: str,
) -> PuzzleResult:
    """Create a consistent failed result."""

    return PuzzleResult(
        concept=concept,
        solved=False,
        reason=reason,
        score=0.0,
    )


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """Convert an input to an integer without raising."""

    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _valid_concept(concept: str) -> bool:
    return concept in VALID_CONCEPTS


# ---------------------------------------------------------------------
# Deterministic sequence interpreter
# ---------------------------------------------------------------------

def simulate_sequence(
    grid: dict[str, Any],
    ops: list[str],
) -> dict[str, Any]:
    """Walk a guardian across a grid.

    Pure function: it never changes the supplied grid.
    """

    if not isinstance(grid, dict):
        raise ValueError("Grid must be an object.")

    try:
        start = grid["start"]
        goal = grid["goal"]

        x = int(start["x"])
        y = int(start["y"])
        facing = str(start["dir"]).upper()

        width = int(grid["w"])
        height = int(grid["h"])

        goal_x = int(goal[0])
        goal_y = int(goal[1])

    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError(
            "Grid definition is incomplete or invalid."
        ) from exc

    if width <= 0 or height <= 0:
        raise ValueError("Grid dimensions must be positive.")

    if facing not in _DIRECTION:
        raise ValueError("Guardian has an invalid starting direction.")

    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("Guardian starts outside the grid.")

    if not (0 <= goal_x < width and 0 <= goal_y < height):
        raise ValueError("Goal is outside the grid.")

    walls: set[tuple[int, int]] = set()

    for wall in grid.get("walls", []):
        if not isinstance(wall, (list, tuple)) or len(wall) != 2:
            raise ValueError("Grid contains an invalid wall.")

        try:
            wall_x = int(wall[0])
            wall_y = int(wall[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Grid contains an invalid wall.") from exc

        if not (0 <= wall_x < width and 0 <= wall_y < height):
            raise ValueError("A wall is outside the grid.")

        walls.add((wall_x, wall_y))

    if (x, y) in walls:
        raise ValueError("Guardian cannot start inside a wall.")

    if (goal_x, goal_y) in walls:
        raise ValueError("Goal cannot be inside a wall.")

    if not isinstance(ops, list):
        raise ValueError("Commands must be supplied as a list.")

    if len(ops) > MAX_SCRIPT_OPS:
        raise ValueError(
            f"A program cannot contain more than {MAX_SCRIPT_OPS} commands."
        )

    path: list[list[int]] = [[x, y]]
    bumped = 0

    for op in ops:
        if op not in LEGAL_OPS:
            raise ValueError(
                f"Unknown command: {op!r}"
            )

        if op == "forward":
            dx, dy = _DIRECTION[facing]

            nx = x + dx
            ny = y + dy

            if (
                0 <= nx < width
                and 0 <= ny < height
                and (nx, ny) not in walls
            ):
                x, y = nx, ny
            else:
                bumped += 1

        elif op == "turn_right":
            facing = _TURN_RIGHT[facing]

        elif op == "turn_left":
            facing = _TURN_LEFT[facing]

        path.append([x, y])

    return {
        "path": path,
        "position": [x, y],
        "facing": facing,
        "reached": [x, y] == [goal_x, goal_y],
        "bumped": bumped,
        "grid": grid,
    }


# ---------------------------------------------------------------------
# Conditions interpreter
# ---------------------------------------------------------------------

def _condition_holds(
    expression: str,
    scenario: dict[str, bool],
) -> bool:
    """Tiny whitelisted boolean interpreter.

    Deliberately does not use eval().
    """

    if not isinstance(expression, str):
        return False

    if not isinstance(scenario, dict):
        return False

    expr = expression.strip().lower()

    if not expr:
        return False

    if " and " in expr:
        return all(
            _condition_holds(part, scenario)
            for part in expr.split(" and ")
        )

    if " or " in expr:
        return any(
            _condition_holds(part, scenario)
            for part in expr.split(" or ")
        )

    if expr.startswith("not "):
        return not _condition_holds(
            expr[4:],
            scenario,
        )

    # Only explicitly defined scenario facts are accepted.
    value = scenario.get(expr, False)

    return value is True


def evaluate_rule(
    rule: dict[str, Any],
    scenario: dict[str, bool],
) -> str:
    """Run one player-authored rule against one situation."""

    if not isinstance(rule, dict):
        return "wait"

    if not isinstance(scenario, dict):
        return "wait"

    if _condition_holds(
        str(rule.get("condition", "")),
        scenario,
    ):
        return str(rule.get("then", "wait"))

    return str(rule.get("else", "wait"))


# ---------------------------------------------------------------------
# Loop interpreter
# ---------------------------------------------------------------------

def expand_blocks(
    blocks: list[dict[str, Any]],
) -> list[str]:
    """Expand player blocks into a flat list of commands.

    A loop is represented as repeated operations.
    Invalid blocks are ignored here, but the puzzle validator rejects them.
    """

    if not isinstance(blocks, list):
        return []

    if len(blocks) > MAX_BLOCKS:
        return []

    ops: list[str] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue

        op = str(block.get("op", "")).strip()

        times = _safe_int(
            block.get("times", 1),
            default=1,
        )

        if times < 1:
            continue

        times = min(times, MAX_SCRIPT_OPS)

        if op == "repeat":
            inner = str(
                block.get("inner", "forward")
            ).strip()

            if inner in LEGAL_OPS:
                ops.extend([inner] * times)

        elif op in LEGAL_OPS:
            ops.extend([op] * times)

        if len(ops) > MAX_SCRIPT_OPS:
            return ops[:MAX_SCRIPT_OPS]

    return ops


# ---------------------------------------------------------------------
# Learning progression
# ---------------------------------------------------------------------

def concept_unlocked(
    learning: LearningProgress,
    concept: str,
) -> bool:
    """A concept unlocks only after the previous concept is solved.

    Unknown concepts return False instead of raising ValueError.
    """

    if not _valid_concept(concept):
        return False

    if not isinstance(learning, LearningProgress):
        return False

    index = CONCEPT_ORDER.index(concept)

    for previous in CONCEPT_ORDER[:index]:
        record = learning.records.get(previous)

        if not record or record.successes < 1:
            return False

    return True


def next_concept(
    learning: LearningProgress,
) -> str:
    """Return the next unsolved concept.

    Once every concept has been solved, the final concept remains
    available for continued practice.
    """

    for concept in CONCEPT_ORDER:
        record = learning.records.get(concept)

        if not record or record.successes < 1:
            return concept

    return CONCEPT_ORDER[-1]


# ---------------------------------------------------------------------
# Puzzle prompt creation
# ---------------------------------------------------------------------

def get_puzzle_prompt(
    learning: LearningProgress,
    concept: str | None = None,
) -> PuzzlePrompt:
    """Create a prompt using the curated puzzle definitions."""

    data = load_puzzles()

    concept = concept or next_concept(learning)

    if not _valid_concept(concept):
        raise ValueError(
            f"Unknown programming concept: {concept!r}"
        )

    pack = data[concept]

    variant = _pick_variant(
        pack["variants"],
        learning.next_difficulty,
    )

    return PuzzlePrompt(
        puzzle_id=(
            f"{concept}-d{variant['difficulty']}"
        ),
        concept=concept,
        title=pack["title"],
        instructions=pack["instructions"],
        difficulty=int(variant["difficulty"]),
        spec=variant,
        max_ops=int(
            variant.get("max_ops", MAX_SCRIPT_OPS)
        ),
        max_blocks=int(
            variant.get("max_blocks", 3)
        ),
    )


def _pick_variant(
    variants: list[dict[str, Any]],
    difficulty: int,
) -> dict[str, Any]:
    """Select the closest available difficulty variant."""

    if not isinstance(variants, list) or not variants:
        raise ValueError(
            "No puzzle variants are available."
        )

    ordered = sorted(
        variants,
        key=lambda item: int(
            item.get("difficulty", 1)
        ),
    )

    index = max(
        0,
        min(
            len(ordered) - 1,
            _safe_int(difficulty, 1) - 1,
        ),
    )

    return ordered[index]


# ---------------------------------------------------------------------
# Public puzzle validation API
# ---------------------------------------------------------------------

def validate_puzzle(
    concept: str,
    spec: dict[str, Any],
    submission: dict[str, Any],
) -> PuzzleResult:
    """The authority on correctness.

    This function is deterministic and side-effect free.
    """

    if not _valid_concept(concept):
        return _invalid(
            str(concept),
            f"Unknown challenge '{concept}'.",
        )

    if not isinstance(spec, dict):
        return _invalid(
            concept,
            "The challenge definition is invalid.",
        )

    if not isinstance(submission, dict):
        return _invalid(
            concept,
            "Your submission could not be read.",
        )

    try:
        if concept == "sequence":
            return _validate_sequence(spec, submission)

        if concept == "loops":
            return _validate_loops(spec, submission)

        if concept == "conditions":
            return _validate_conditions(spec, submission)

        if concept == "code_assembly":
            return _validate_assembly(spec, submission)

    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return _invalid(
            concept,
            (
                "The challenge could not evaluate that attempt. "
                "Check your commands and try again."
            ),
        )

    return _invalid(
        concept,
        f"Unknown challenge '{concept}'.",
    )


# ---------------------------------------------------------------------
# Sequence validation
# ---------------------------------------------------------------------

def _validate_sequence(
    spec: dict[str, Any],
    submission: dict[str, Any],
) -> PuzzleResult:
    ops = submission.get("ops", [])

    if not isinstance(ops, list):
        return _invalid(
            "sequence",
            "Commands must be submitted as a list.",
        )

    if not ops:
        return _invalid(
            "sequence",
            "The guardian received no commands.",
        )

    if len(ops) > int(
        spec.get("max_ops", MAX_SCRIPT_OPS)
    ):
        return _invalid(
            "sequence",
            (
                f"That is {len(ops)} commands; "
                f"the scroll holds only {spec.get('max_ops')}."
            ),
        )

    # Do not silently discard unknown commands.
    invalid_ops = [
        op for op in ops
        if not isinstance(op, str) or op not in LEGAL_OPS
    ]

    if invalid_ops:
        return _invalid(
            "sequence",
            "One or more commands are not recognised.",
        )

    trace = simulate_sequence(
        spec["grid"],
        ops,
    )

    if not trace["reached"]:
        return PuzzleResult(
            concept="sequence",
            solved=False,
            reason=(
                f"The guardian stopped at {trace['position']} "
                "and never reached the goal."
            ),
            trace=trace,
        )

    return PuzzleResult(
        concept="sequence",
        solved=True,
        reason="The guardian reached the far tile.",
        score=(
            1.0 if trace["bumped"] == 0 else 0.8
        ),
        trace=trace,
    )


# ---------------------------------------------------------------------
# Loop validation
# ---------------------------------------------------------------------

def _validate_loops(
    spec: dict[str, Any],
    submission: dict[str, Any],
) -> PuzzleResult:
    blocks = submission.get("blocks", [])

    if not isinstance(blocks, list):
        return _invalid(
            "loops",
            "Loop blocks must be submitted as a list.",
        )

    if not blocks:
        return _invalid(
            "loops",
            "No blocks were placed on the river.",
        )

    max_blocks = _safe_int(
        spec.get("max_blocks", 3),
        3,
    )

    if len(blocks) > max_blocks:
        return _invalid(
            "loops",
            (
                "Too many blocks — the whole point is "
                "to repeat instead of repeating yourself."
            ),
        )

    for block in blocks:
        if not isinstance(block, dict):
            return _invalid(
                "loops",
                "One of your blocks is invalid.",
            )

        op = str(block.get("op", "")).strip()

        if op == "repeat":
            inner = str(
                block.get("inner", "forward")
            ).strip()

            if inner not in LEGAL_OPS:
                return _invalid(
                    "loops",
                    "Your repeat block contains an unknown command.",
                )

        elif op not in LEGAL_OPS:
            return _invalid(
                "loops",
                "Your program contains an unknown block.",
            )

        times = _safe_int(
            block.get("times", 1),
            1,
        )

        if times < 1 or times > MAX_SCRIPT_OPS:
            return _invalid(
                "loops",
                "A repeat block must have a valid positive count.",
            )

    ops = expand_blocks(blocks)

    if not ops:
        return _invalid(
            "loops",
            "Your program does not contain any executable commands.",
        )

    if len(ops) > MAX_SCRIPT_OPS:
        return _invalid(
            "loops",
            "Your program contains too many commands.",
        )

    steps = _safe_int(
        spec.get("steps", 0),
        0,
    )

    if steps <= 0:
        return _invalid(
            "loops",
            "This river challenge has an invalid length.",
        )

    grid = {
        "w": steps + 1,
        "h": 1,
        "walls": [],
        "start": {
            "x": 0,
            "y": 0,
            "dir": "E",
        },
        "goal": [steps, 0],
    }

    trace = simulate_sequence(
        grid,
        ops,
    )

    if trace["reached"]:
        return PuzzleResult(
            concept="loops",
            solved=True,
            reason="The guardian crossed the hollow river.",
            score=1.0,
            trace=trace,
        )

    return PuzzleResult(
        concept="loops",
        solved=False,
        reason=(
            f"The guardian is at tile "
            f"{trace['position'][0]} of {steps}."
        ),
        trace=trace,
    )


# ---------------------------------------------------------------------
# Conditional logic validation
# ---------------------------------------------------------------------

def _validate_conditions(
    spec: dict[str, Any],
    submission: dict[str, Any],
) -> PuzzleResult:
    scenarios = spec.get("scenarios", [])

    if not isinstance(scenarios, list) or not scenarios:
        return _invalid(
            "conditions",
            "This challenge has no valid situations to test.",
        )

    rule = {
        "condition": str(
            submission.get("condition", "")
        ),
        "then": str(
            submission.get("then", "wait")
        ),
        "else": str(
            submission.get("else", "wait")
        ),
    }

    if not rule["condition"].strip():
        return _invalid(
            "conditions",
            "Your rule needs a condition.",
        )

    outcomes = []

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            return _invalid(
                "conditions",
                "One of the test situations is invalid.",
            )

        facts = scenario.get("facts", {})

        if not isinstance(facts, dict):
            return _invalid(
                "conditions",
                "One of the situation facts is invalid.",
            )

        expected = str(
            scenario.get("expect", "wait")
        )

        got = evaluate_rule(
            rule,
            facts,
        )

        outcomes.append(
            {
                "facts": facts,
                "expected": expected,
                "got": got,
                "ok": got == expected,
            }
        )

    failures = [
        item for item in outcomes
        if not item["ok"]
    ]

    if failures:
        first = failures[0]

        return PuzzleResult(
            concept="conditions",
            solved=False,
            reason=(
                "The door-keeper fails in one situation: "
                f"with {first['facts']} it should "
                f"{first['expected']} but your rule says "
                f"{first['got']}."
            ),
            trace={
                "outcomes": outcomes,
            },
        )

    return PuzzleResult(
        concept="conditions",
        solved=True,
        reason=(
            "Your rule holds in every situation "
            "the door-keeper knows."
        ),
        score=1.0,
        trace={
            "outcomes": outcomes,
        },
    )


# ---------------------------------------------------------------------
# Code assembly validation
# ---------------------------------------------------------------------

def _validate_assembly(
    spec: dict[str, Any],
    submission: dict[str, Any],
) -> PuzzleResult:
    chosen = submission.get("lines", [])
    solution = spec.get("solution", [])

    if not isinstance(chosen, list):
        return _invalid(
            "code_assembly",
            "Code lines must be submitted as a list.",
        )

    if not isinstance(solution, list) or not solution:
        return _invalid(
            "code_assembly",
            "This code assembly challenge has an invalid solution.",
        )

    chosen = [str(line) for line in chosen]
    solution = [str(line) for line in solution]

    if chosen == solution:
        return PuzzleResult(
            concept="code_assembly",
            solved=True,
            reason="The scroll is restored.",
            score=1.0,
            trace={
                "lines": chosen,
            },
        )

    correct = sum(
        1
        for actual, expected in zip(chosen, solution)
        if actual == expected
    )

    return PuzzleResult(
        concept="code_assembly",
        solved=False,
        reason=(
            f"{correct} of {len(solution)} lines "
            "sit in the right place."
        ),
        trace={
            "lines": chosen,
        },
    )


# ---------------------------------------------------------------------
# Learning progress recording
# ---------------------------------------------------------------------

def record_attempt(
    learning: LearningProgress,
    concept: str,
    result: PuzzleResult,
    hints_used: int = 0,
    difficulty: int = 1,
) -> LearningProgress:
    """Record learning progress from an objective outcome.

    Narration and AI-generated text never write learning progress.
    """

    if not _valid_concept(concept):
        raise ValueError(
            f"Cannot record an unknown concept: {concept!r}"
        )

    if not isinstance(learning, LearningProgress):
        raise TypeError(
            "Expected a LearningProgress object."
        )

    if not isinstance(result, PuzzleResult):
        raise TypeError(
            "Expected a PuzzleResult object."
        )

    if result.concept != concept:
        raise ValueError(
            "The puzzle result does not match the submitted concept."
        )

    hints_used = max(
        0,
        min(
            _safe_int(hints_used, 0),
            MAX_HINTS,
        ),
    )

    difficulty = max(
        1,
        min(
            _safe_int(difficulty, 1),
            10,
        ),
    )

    record = learning.record(concept)

    record.introduced = True
    record.attempts += 1
    record.hints_used += hints_used
    record.difficulty = difficulty

    if result.solved:
        record.successes += 1

        if record.attempts == 1:
            record.first_try_successes += 1

        record.revealed = True

        if concept not in learning.revealed:
            learning.revealed.append(concept)

    # Advance the stage only when the relevant concept
    # has demonstrably been solved.
    if concept_unlocked(learning, "conditions"):
        learning.stage = max(
            learning.stage,
            1,
        )

    if concept_unlocked(learning, "loops"):
        learning.stage = max(
            learning.stage,
            2,
        )

    if concept_unlocked(learning, "code_assembly"):
        learning.stage = max(
            learning.stage,
            3,
        )

    learning.active_concept = next_concept(learning)

    return learning


# ---------------------------------------------------------------------
# Curated learning reveals and hints
# ---------------------------------------------------------------------

def concept_reveal(
    concept: str,
) -> ConceptReveal:
    """Return the curated Python explanation for a concept."""

    if not _valid_concept(concept):
        raise ValueError(
            f"Unknown concept: {concept!r}"
        )

    pack = load_puzzles()[concept]

    return ConceptReveal(
        **pack["reveal"]
    )


def static_hint(
    concept: str,
    difficulty: int = 1,
) -> str:
    """Return a curated hint for the selected difficulty."""

    if not _valid_concept(concept):
        raise ValueError(
            f"Unknown concept: {concept!r}"
        )

    pack = load_puzzles()[concept]

    variant = _pick_variant(
        pack["variants"],
        difficulty,
    )

    return (
        str(variant.get("hint", "")).strip()
        or (
            "Read the world carefully; "
            "the rule is hidden in what repeats."
        )
    )


# ---------------------------------------------------------------------
# Player program descriptions
# ---------------------------------------------------------------------

def describe_program(
    concept: str,
    submission: dict[str, Any],
) -> str:
    """Create a human-readable recap for the learning journal."""

    if not isinstance(submission, dict):
        return "(invalid program)"

    if concept == "sequence":
        return " → ".join(
            str(op).replace("_", " ")
            for op in submission.get("ops", [])
        ) or "(empty scroll)"

    if concept == "loops":
        parts = []

        for block in submission.get("blocks", []):
            if not isinstance(block, dict):
                continue

            if str(block.get("op")) == "repeat":
                parts.append(
                    f"repeat {block.get('inner')} "
                    f"x{block.get('times')}"
                )
            else:
                parts.append(
                    f"{block.get('op')} "
                    f"x{block.get('times')}"
                )

        return " → ".join(parts) or "(empty scroll)"

    if concept == "conditions":
        return (
            f"if {submission.get('condition')} "
            f"then {submission.get('then')} "
            f"else {submission.get('else')}"
        )

    if concept == "code_assembly":
        return " · ".join(
            str(line)
            for line in submission.get("lines", [])
        )

    return ""


# ---------------------------------------------------------------------
# Safe invention composition
# ---------------------------------------------------------------------

def compose_invention(
    name: str,
    blocks: list[dict[str, Any]],
    turn: int,
) -> Invention:
    """Create a deterministic player-made magical invention."""

    if not isinstance(blocks, list):
        blocks = []

    parsed = [
        InventionBlock(**block)
        for block in blocks[:6]
        if isinstance(block, dict)
    ]

    effect_bits = []

    for block in parsed:
        if block.kind == "repeat":
            effect_bits.append(
                f"repeats {block.inner or 'action'} ×{block.times}"
            )

        elif block.kind == "if":
            effect_bits.append(
                f"decides when {block.condition or 'a condition holds'}"
            )

        elif block.kind == "glow":
            effect_bits.append(
                "sheds steady light"
            )

        else:
            effect_bits.append(
                block.kind.replace("_", " ")
            )

    if effect_bits:
        effect = (
            "This device "
            + ", ".join(effect_bits[:4])
            + "."
        )
    else:
        effect = "The device hums, unfinished."

    return Invention(
        name=(
            str(name).strip()[:48]
            or "Unnamed Device"
        ),
        blocks=parsed,
        effect=effect,
        created_turn=max(
            0,
            _safe_int(turn, 0),
        ),
    )
