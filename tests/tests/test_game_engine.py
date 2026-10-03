"""New game, character creation, turns, persistence, reload — all offline."""
from __future__ import annotations

from core import game_engine
from models.story import Scene


def test_new_game_initialisation(game):
    assert game.turn == 0
    assert game.world.kingdom == "Elarion"
    assert game.quest.quest_id == "silent_water"
    assert game.learning.active_concept == "sequence"
    assert set(game.characters) >= {"mira", "nettle", "sable"}


def test_character_creation_records_names(game):
    state = game_engine.new_session("Aria", "Inventor", "Bold")
    assert state.player.name == "Aria"
    assert state.player.role == "Inventor"
    assert state.player.style == "Bold"


def test_character_creation_does_not_set_ability(game):
    state = game_engine.new_session("Aria", "Beast-Speaker", "Bold")
    assert state.player.concept_mastery.sequence == 0.0
    assert state.player.challenge_level == 1


def test_opening_scene_offers_real_choices(game):
    state = game_engine.opening_scene(game)
    assert state.last_scene is not None
    assert 2 <= len(state.last_scene.actions) <= 5


def test_offline_turn_produces_a_scene(game):
    state = game_engine.opening_scene(game)
    result = game_engine.act(state, state.last_scene.actions[0].action_id)
    assert result.ok is True
    assert isinstance(result.scene, Scene)
    assert result.scene.actions, "a scene must always offer the player choices"


def test_turn_increments_and_records_history(game):
    state = game_engine.opening_scene(game)
    game_engine.act(state, state.last_scene.actions[0].action_id)
    assert state.turn == 1
    assert state.recent_history


def test_safety_blocks_unverified_progress_claims(game):
    from agents.continuity_safety_agent import local_review
    from models.story import Scene, SceneAction

    bad = Scene(
        title="Triumph",
        description="You have mastered the ancient art of loops.",
        actions=[SceneAction(action_id="go", label="Continue")],
    )
    verdict = local_review(game, bad, [], None)
    assert verdict.approved is False
    assert any("progress" in issue for issue in verdict.issues)


def test_safety_blocks_graphic_content(game):
    from agents.continuity_safety_agent import local_review
    from models.story import Scene, SceneAction

    bad = Scene(
        title="Gore",
        description="The guardian is beheaded and the torture continues.",
        actions=[SceneAction(action_id="go", label="Continue")],
    )
    assert local_review(game, bad, [], None).approved is False


def test_safe_scene_is_always_available(game):
    from agents.continuity_safety_agent import safe_scene

    scene = safe_scene(game)
    assert scene.actions and scene.description


def test_persistence_and_reload(game, tmp_path):
    from database.storage import get_storage

    state = game_engine.opening_scene(game)
    game_engine.act(state, state.last_scene.actions[0].action_id)
    session_id = state.session_id

    from database.storage import reset_storage_cache

    reset_storage_cache()
    reloaded = get_storage().load_game(session_id)
    assert reloaded is not None
    assert reloaded.turn == state.turn
    assert reloaded.player.name == state.player.name
    assert reloaded.world.water_supply == state.world.water_supply


def test_corrupted_save_returns_none_not_crash(game):
    from database.storage import get_storage

    storage = get_storage()
    storage.save_game(game)
    with storage._lock:
        storage.conn.execute("UPDATE saves SET payload = ? WHERE session_id = ?", ("{not json", game.session_id))
        storage.conn.commit()
    assert storage.load_game(game.session_id) is None


def test_travel_only_to_discovered_places(game):
    assert game_engine.travel_to(game, "Atlantis") is False
    assert game_engine.travel_to(game, "Whispering Village") is True


def test_discovery_is_monotonic(game):
    game_engine.discover(game, "Sunken Cistern")
    game_engine.discover(game, "Sunken Cistern")
    assert game.world.discovered_locations.count("Sunken Cistern") == 1


def test_invention_is_recorded(game):
    effect = game_engine.craft_invention(game, "Tireless Lantern", [{"kind": "glow", "times": 1}])
    assert "light" in effect
    assert game.inventions and game.inventions[-1].name == "Tireless Lantern"


def test_reset_clears_all_saves(game):
    from database.storage import get_storage

    storage = get_storage()
    game_engine.opening_scene(game)
    assert storage.latest_session_id() is not None
    game_engine.reset_all()
    assert storage.latest_session_id() is None


def test_offline_director_is_reproducible(game):
    from agents.director_agent import offline_plan

    first = offline_plan(game, "Look around", "explore")
    second = offline_plan(game, "Look around", "explore")
    assert first.model_dump() == second.model_dump()
