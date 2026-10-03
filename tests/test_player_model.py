"""Bounded, reversible adaptation. No sensitive inference."""
from __future__ import annotations

from core import player_model as pm
from models.player import MAX_STEP, PlayerProfile, ProfileUpdate


def test_default_profile_has_no_labels():
    profile = pm.default_profile("Wren", "Inventor", "Curious")
    assert profile.role == "Inventor"
    assert profile.confidence < 0.2
    assert not hasattr(profile, "personality")
    assert not hasattr(profile, "intelligence")


def test_single_action_moves_estimates_by_at_most_max_step():
    profile = pm.default_profile("Wren", "Wanderer", "Curious")
    before = profile.exploration_preference
    pm.observe(profile, "explore")
    assert abs(profile.exploration_preference - before) <= MAX_STEP


def test_huge_llm_delta_is_clamped():
    profile = pm.default_profile("Wren", "Wanderer", "Curious")
    before = profile.puzzle_preference
    pm.apply_update(profile, ProfileUpdate(deltas={"puzzle_preference": 99.0}))
    assert abs(profile.puzzle_preference - before) <= MAX_STEP


def test_unknown_dimension_is_ignored():
    profile = pm.default_profile("Wren", "Wanderer", "Curious")
    pm.apply_update(profile, ProfileUpdate(deltas={"intelligence": 1.0, "iq": 1.0}))
    assert not hasattr(profile, "intelligence")
    assert not hasattr(profile, "iq")


def test_estimates_stay_in_range_over_many_actions():
    profile = pm.default_profile("Wren", "Wanderer", "Curious")
    for _ in range(200):
        pm.observe(profile, "explore")
    assert 0.0 <= profile.exploration_preference <= 1.0


def test_adaptation_is_reversible():
    profile = pm.default_profile("Wren", "Wanderer", "Curious")
    pm.observe(profile, "explore")
    raised = profile.exploration_preference
    pm.observe(profile, "rest")
    pm.apply_update(profile, ProfileUpdate(deltas={"exploration_preference": -MAX_STEP}))
    assert profile.exploration_preference < raised


def test_confidence_grows_and_never_exceeds_one():
    profile = pm.default_profile("Wren", "Wanderer", "Curious")
    for _ in range(80):
        pm.observe(profile, "talk")
    assert 0.0 < profile.confidence <= 1.0


def test_first_try_mastery_beats_hinted_mastery():
    a = pm.default_profile("A", "Wanderer", "Curious")
    b = pm.default_profile("B", "Wanderer", "Curious")
    pm.mastery_after(a, "sequence", solved=True, first_try=True, hints_used=0)
    pm.mastery_after(b, "sequence", solved=True, first_try=True, hints_used=2)
    assert a.concept_mastery.sequence > b.concept_mastery.sequence


def test_failure_reduces_mastery_but_never_below_zero():
    profile = pm.default_profile("A", "Wanderer", "Curious")
    for _ in range(20):
        pm.mastery_after(profile, "loops", solved=False, first_try=False, hints_used=0)
    assert profile.concept_mastery.loops == 0.0


def test_difficulty_recommendation_is_bounded(game):
    assert pm.recommend_difficulty(game.player, game.learning) in (1, 2, 3)
    game.player.concept_mastery.sequence = 0.95
    game.player.challenge_tolerance = 0.8
    assert pm.recommend_difficulty(game.player, game.learning) == 3


def test_serialisation_round_trip():
    profile = PlayerProfile(player_id="p1", name="Wren")
    again = PlayerProfile.model_validate_json(profile.model_dump_json())
    assert again == profile
