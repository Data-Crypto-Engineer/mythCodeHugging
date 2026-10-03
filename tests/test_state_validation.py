"""Valid world-state changes are accepted; invalid ones are REJECTED and nothing is lost."""
from __future__ import annotations

from core.state_validator import apply_changes, validate_changes, validate_state
from models.world import ProposedChange


def test_new_game_state_is_valid(game):
    assert validate_state(game) == []
    assert game.world.current_location in game.world.discovered_locations


def test_out_of_range_numbers_are_clamped(game):
    game.world.village_morale = 900
    game.world.forest_spirit_trust = -9999
    problems = validate_state(game)
    assert game.world.village_morale == 100
    assert game.world.forest_spirit_trust == -100
    assert any("morale" in problem for problem in problems)


def test_illegal_enum_becomes_unknown(game):
    game.world.water_supply = "exploded"
    validate_state(game)
    assert game.world.water_supply == "unknown"


def test_undiscovered_location_is_refused(game):
    accepted, rejected = validate_changes(
        game, [ProposedChange(key="current_location", new_value="Atlantis")]
    )
    assert accepted == []
    assert any("undiscovered" in problem for problem in rejected)


def test_discovered_location_is_accepted(game):
    game.world.discovered_locations.append("Sunken Cistern")
    accepted, rejected = validate_changes(
        game, [ProposedChange(key="current_location", new_value="Sunken Cistern")]
    )
    assert len(accepted) == 1 and not rejected
    apply_changes(game, accepted)
    assert game.world.current_location == "Sunken Cistern"


def test_history_is_never_lost(game):
    game.world.discovered_locations = ["Whispering Village", "Sunken Cistern"]
    accepted, rejected = validate_changes(
        game, [ProposedChange(key="discovered_locations", new_value="Whispering Village")]
    )
    assert accepted == []
    assert any("append-only" in problem for problem in rejected)


def test_completed_quests_are_append_only(game):
    game.world.completed_quests = ["silent_water"]
    _, rejected = validate_changes(
        game, [ProposedChange(key="completed_quests", new_value="")]
    )
    assert rejected
    assert game.world.completed_quests == ["silent_water"]


def test_restored_water_cannot_regress(game):
    game.world.water_supply = "restored"
    accepted, rejected = validate_changes(
        game, [ProposedChange(key="water_supply", new_value="damaged")]
    )
    assert accepted == [] and rejected


def test_guardian_cannot_unwake(game):
    game.world.clockwork_guardian = "awakened"
    accepted, rejected = validate_changes(
        game, [ProposedChange(key="clockwork_guardian", new_value="stirring")]
    )
    assert accepted == [] and rejected


def test_guardian_advances_legally(game):
    accepted, _ = validate_changes(
        game, [ProposedChange(key="clockwork_guardian", new_value="stirring")]
    )
    assert accepted[0].new_value == "stirring"


def test_unknown_keys_are_rejected(game):
    accepted, rejected = validate_changes(game, [ProposedChange(key="player_is_smart", new_value="true")])
    assert accepted == []
    assert any("unknown state key" in problem for problem in rejected)
