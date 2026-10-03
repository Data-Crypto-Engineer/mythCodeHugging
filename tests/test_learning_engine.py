"""Deterministic puzzle verdicts + learning progression from OBJECTIVE outcomes."""
from __future__ import annotations

from core import learning_engine as le


def test_sequence_solved():
    spec = le.load_puzzles()["sequence"]["variants"][0]
    grid = spec["grid"]
    ops = []
    # walk east along the top lane, then south to the goal
    ops += ["forward"] * (grid["goal"][0] - grid["start"]["x"])
    result = le.validate_puzzle("sequence", spec, {"ops": ops})
    assert result.solved is True


def test_sequence_rejected_when_wall_blocks():
    spec = le.load_puzzles()["sequence"]["variants"][0]
    result = le.validate_puzzle("sequence", spec, {"ops": ["forward"] * 8})
    assert result.solved is False
    assert result.trace["bumped"] > 0


def test_sequence_rejects_empty_script():
    spec = le.load_puzzles()["sequence"]["variants"][0]
    assert le.validate_puzzle("sequence", spec, {"ops": []}).solved is False


def test_sequence_enforces_operation_budget():
    spec = le.load_puzzles()["sequence"]["variants"][0]
    assert le.validate_puzzle("sequence", spec, {"ops": ["turn_left"] * 20}).solved is False


def test_conditions_solved_by_correct_rule():
    spec = le.load_puzzles()["conditions"]["variants"][0]
    result = le.validate_puzzle(
        "conditions", spec, {"condition": "has_key", "then": "open_door", "else": "search_for_key"}
    )
    assert result.solved is True
    assert all(outcome["ok"] for outcome in result.trace["outcomes"])


def test_conditions_fails_in_one_scenario():
    spec = le.load_puzzles()["conditions"]["variants"][0]
    result = le.validate_puzzle(
        "conditions", spec, {"condition": "has_key", "then": "open_door", "else": "open_door"}
    )
    assert result.solved is False
    assert "door-keeper fails" in result.reason


def test_conditions_difficulty_two_requires_ordered_logic():
    spec = le.load_puzzles()["conditions"]["variants"][1]
    assert le.validate_puzzle(
        "conditions", spec, {"condition": "has_key", "then": "open_door", "else": "search_for_key"}
    ).solved is False
    assert le.validate_puzzle(
        "conditions", spec, {"condition": "has_key", "then": "open_door", "else": "light_lantern"}
    ).solved is False  # the lantern branch must not fire when a lantern is absent


def test_loops_require_repetition_not_repetition_of_blocks():
    spec = le.load_puzzles()["loops"]["variants"][0]
    good = le.validate_puzzle("loops", spec, {"blocks": [{"op": "repeat", "inner": "forward", "times": spec["steps"]}]})
    assert good.solved is True
    too_many = le.validate_puzzle(
        "loops", spec, {"blocks": [{"op": "forward", "times": 1} for _ in range(spec["steps"])]}
    )
    assert too_many.solved is False


def test_no_eval_or_exec_anywhere():
    import inspect

    source = inspect.getsource(le)
    assert "eval(" not in source
    assert "exec(" not in source


def test_assembly_requires_exact_order():
    spec = le.load_puzzles()["code_assembly"]["variants"][0]
    assert le.validate_puzzle("code_assembly", spec, {"lines": spec["solution"]}).solved is True
    assert le.validate_puzzle("code_assembly", spec, {"lines": list(reversed(spec["solution"]))}).solved is False


def test_learning_progress_written_from_outcome(game):
    spec = le.load_puzzles()["sequence"]["variants"][0]
    solved = le.PuzzleResult(concept="sequence", solved=True, score=1.0)
    le.record_attempt(game.learning, "sequence", solved, hints_used=0, difficulty=1)
    record = game.learning.records["sequence"]
    assert record.successes == 1 and record.first_try_successes == 1
    assert "sequence" in game.learning.revealed
    assert game.learning.active_concept == "conditions"


def test_failed_attempt_does_not_reveal(game):
    failed = le.PuzzleResult(concept="sequence", solved=False, reason="stopped short")
    le.record_attempt(game.learning, "sequence", failed, hints_used=2, difficulty=1)
    record = game.learning.records["sequence"]
    assert record.successes == 0 and record.hints_used == 2 and not record.revealed


def test_staged_unlocking_is_enforced(game):
    assert le.concept_unlocked(game.learning, "sequence") is True
    assert le.concept_unlocked(game.learning, "loops") is False
    solved = le.PuzzleResult(concept="sequence", solved=True, score=1.0)
    le.record_attempt(game.learning, "sequence", solved)
    solved_c = le.PuzzleResult(concept="conditions", solved=True, score=1.0)
    le.record_attempt(game.learning, "conditions", solved_c)
    assert le.concept_unlocked(game.learning, "loops") is True


def test_reveal_is_data_not_generation():
    reveal = le.concept_reveal("loops")
    assert reveal.python_example.strip().startswith("for")
    assert "range" in reveal.python_example


def test_invention_composition_is_safe():
    invention = le.compose_invention("Lantern", [{"kind": "glow", "times": 1}], turn=3)
    assert "light" in invention.effect
    assert invention.name == "Lantern"


def test_seeded_sequence_simulation_is_reproducible():
    spec = le.load_puzzles()["sequence"]["variants"][1]
    first = le.simulate_sequence(spec["grid"], ["forward", "turn_right", "forward"])
    second = le.simulate_sequence(spec["grid"], ["forward", "turn_right", "forward"])
    assert first == second
