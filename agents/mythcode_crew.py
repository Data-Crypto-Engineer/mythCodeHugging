"""CrewAI Flow orchestration — the ONLY entry point the UI calls.

Verified API surface used here:
  from crewai.flow.flow import Flow, listen, start, router, or_
  Pydantic state via Flow[State];  @router returns a string label;
  @listen("label") binds to it;  .kickoff() runs the flow.

Conditional execution (a dialogue turn never pays for the learning agent):
  action ──> director ──> {insight} ──> {world} ──> {story | challenge} ──> safety
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.game import GameState, TurnResult
from models.story import Scene, SceneAction
from utils.logger import get_logger
from utils.validators import scrub_text

logger = get_logger("flow")


class TurnState(BaseModel):
    """Flow-local working memory. Deliberately NOT the game state itself."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    game: GameState
    action_id: str = ""
    action_label: str = "The player hesitates"
    action_kind: str = "explore"
    requested_concept: str = ""
    context_block: str = ""
    plan: Any = None
    scene: Any = None
    changes: list[Any] = Field(default_factory=list)
    safety: Any = None
    reveal: Any = None
    puzzle_prompt: Any = None
    puzzle_result: Any = None
    submission: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    degraded: bool = False


def _find_action(game: GameState, action_id: str) -> SceneAction:
    if game.last_scene:
        for action in game.last_scene.actions:
            if action.action_id == action_id:
                return action
    return SceneAction(action_id=action_id or "unknown", label=action_id.replace("_", " ") or "Act", kind="explore")


def _build_flow() -> Any:
    """Build the Flow lazily so importing this module never requires CrewAI."""
    from crewai.flow.flow import Flow, listen, router, start

    from agents import continuity_safety_agent as safety_agent
    from agents import director_agent, logic_learning_agent, player_insight_agent
    from agents import story_weaver_agent, world_keeper_agent
    from core import learning_engine
    from core import state_manager, state_validator

    class MythCodeFlow(Flow[TurnState]):
        """One player action, end to end, with validation before persistence."""

        # ── 1. interpret ────────────────────────────────────────
        @start()
        def open_turn(self):
            action = _find_action(self.state.game, self.state.action_id)
            self.state.action_label = action.label
            self.state.action_kind = action.kind
            self.state.requested_concept = action.concept or ""
            self.state.context_block = state_manager.summary_of(self.state.game)
            self.state.notes.append(f"Action '{action.label}' classified as {action.kind}.")

        # ── 2. route by action kind (conditional execution) ─────
        @router(open_turn)
        def route_action(self):
            if self.state.action_kind == "puzzle" or self.state.requested_concept:
                return "challenge"
            return "normal"

        # ── 3a. normal narrative path ───────────────────────────
        @listen("normal")
        def direct_turn(self):
            self.state.plan = director_agent.plan_turn(
                self.state.game, self.state.action_label, self.state.action_kind, self.state.context_block
            )
            self.state.notes.append(f"Director chose category '{self.state.plan.event_category}'.")

        # ── 3b. challenge path ──────────────────────────────────
        @listen("challenge")
        def prepare_challenge(self):
            from core.learning_engine import concept_unlocked, next_concept

            concept = self.state.requested_concept or next_concept(self.state.game.learning)
            if not concept_unlocked(self.state.game.learning, concept):
                self.state.notes.append(f"Concept '{concept}' is still locked; routing to story instead.")
                concept = "none"
            plan = director_agent.offline_plan(self.state.game, self.state.action_label, "puzzle")
            if concept != "none":
                plan.suggested_challenge = concept
                plan.event_category = "puzzle"
                plan.required_agents = ["story", "world", "learning"]
            self.state.plan = plan
            self.state.notes.append(f"Challenge prepared for concept '{concept}'.")

        # ── 4. player model (always, cheaply) ───────────────────
        @listen(or_("direct_turn", "prepare_challenge"))
        def adapt_player(self):
            player_insight_agent.update_profile(
                self.state.game, self.state.action_label, self.state.action_kind, "in progress"
            )

        # ── 5. narrative ────────────────────────────────────────
        @listen(adapt_player)
        def tell_story(self):
            if self.state.plan.suggested_challenge != "none":
                frame = logic_learning_agent.frame_challenge(
                    self.state.game, self.state.plan.suggested_challenge
                )
                self.state.puzzle_prompt = learning_engine.get_puzzle_prompt(
                    self.state.game.learning, self.state.plan.suggested_challenge
                )
                self.state.puzzle_prompt.framing = f"{frame.intro} {frame.flavour}".strip()
            self.state.scene = story_weaver_agent.weave(
                self.state.game, self.state.plan, self.state.action_label
            )

        # ── 6. world continuity ─────────────────────────────────
        @listen(tell_story)
        def keep_world(self):
            patch = world_keeper_agent.propose(
                self.state.game, self.state.scene, self.state.action_label
            )
            if patch is None:
                patch = world_keeper_agent.offline_patch(
                    self.state.game, self.state.scene, self.state.action_label
                )
            self.state.game_patch = patch
            accepted, rejected = state_validator.validate_changes(self.state.game, patch.changes)
            self.state.changes = accepted
            for note in patch.memory_notes:
                state_manager.remember(self.state.game, note.npc_id, note.note)
            self.state.notes.extend(rejected)

        # ── 7. safety gate ──────────────────────────────────────
        @listen(keep_world)
        def guard(self):
            verdict = safety_agent.review(self.state.game, self.state.scene, self.state.changes, self.state.plan)
            self.state.safety = verdict

        @router(guard)
        def decide(self):
            return "blocked" if not self.state.safety.approved else "approved"

        @listen("blocked")
        def rescue(self):
            self.state.scene = safety_agent.safe_scene(self.state.game)
            self.state.changes = []
            self.state.safety = self.state.safety.model_copy(update={"approved": True})
            self.state.degraded = True
            self.state.notes.append("Safety veto — served the predefined safe scene; world state preserved.")

        # ── 8. commit + reveal ──────────────────────────────────
        @listen(or_("approved", rescue))
        def commit(self):
            game = self.state.game
            game = state_validator  # noqa: F841  (clarity: validation lives above)
            applied = state_validator.apply_changes(game, self.state.changes)
            state_manager.add_ledger(game, f"{self.state.action_label} → {', '.join(applied) or 'no world change'}")
            state_manager.append_history(game, f"{self.state.scene.title}: {self.state.scene.description[:120]}")
            state_manager.fold_history(game)
            game.turn += 1
            game.last_scene = self.state.scene
            game.learning.next_difficulty = _difficulty(game)
            state_manager.validate_and_report(game)

            if self.state.plan.suggested_challenge != "none" and self.state.puzzle_prompt is not None:
                record = game.learning.record(self.state.puzzle_prompt.concept)
                record.introduced = True
                self.state.reveal = None  # reveal waits until the puzzle is actually solved

        # ── 9. finish ───────────────────────────────────────────
        @listen(commit)
        def finish(self):
            try:
                from database.storage import get_storage

                get_storage().save_game(self.state.game)
                get_storage().log_turn(
                    self.state.game.session_id, self.state.game.turn,
                    self.state.action_kind, f"{self.state.scene.title}: {self.state.action_label}",
                )
            except Exception as exc:  # saving must never break a turn
                self.state.notes.append(f"Save skipped: {type(exc).__name__}")

    def _difficulty(game: GameState) -> int:
        from core.player_model import recommend_difficulty

        return recommend_difficulty(game.player, game.learning)

    return MythCodeFlow


def process_player_action(
    game: GameState,
    action_id: str,
    submission: dict[str, Any] | None = None,
) -> TurnResult:
    """Application-facing entry point. Never raises; always returns a TurnResult."""
    from core import learning_engine, state_manager, state_validator
    from models.story import Scene, SceneAction
    from utils.error_handler import log_exception

    result = TurnResult()
    snapshot = state_manager.snapshot(game)
    try:
        state_validator.validate_state(game)

        # A puzzle submission is validated deterministically BEFORE any agent runs.
        if submission:
            prompt = learning_engine.get_puzzle_prompt(game.learning, game.learning.active_concept)
            verdict = learning_engine.validate_puzzle(prompt.concept, prompt.spec, submission)
            hints = int(submission.get("hints_used", 0) or 0)
            learning_engine.record_attempt(game.learning, prompt.concept, verdict, hints, prompt.difficulty)
            from core.player_model import mastery_after

            mastery_after(
                game.player, prompt.concept, verdict.solved,
                game.learning.record(prompt.concept).attempts == 1, hints,
            )
            game.learning.next_difficulty = recommend(game)
            result.puzzle_result = (
                f"{'Solved' if verdict.solved else 'Not yet'}: {verdict.reason}"
            )
            state_manager.append_history(game, f"Challenge attempt ({prompt.concept}): {verdict.reason[:90]}")
            if verdict.solved:
                result.reveal = learning_engine.concept_reveal(prompt.concept)
                game.turn += 1
            state_manager.validate_and_report(game)
            _persist(game)
            result.scene = game.last_scene or Scene(
                title="The Scroll Records Your Answer",
                description=verdict.reason,
                actions=_puzzle_followups(game, verdict.solved),
                category="consequence",
                location=game.world.current_location,
            )
            result.scene = _merge_followups(result.scene, _puzzle_followups(game, verdict.solved))
            return result

        FlowClass = _build_flow()
        flow = FlowClass()
        flow.state.game = game
        flow.state.action_id = action_id
        flow.kickoff()

        result.scene = flow.state.scene
        result.puzzle = flow.state.puzzle_prompt
        result.reveal = flow.state.reveal
        result.safety = flow.state.safety
        result.debug = flow.state.notes
        result.state_changed = bool(flow.state.changes)
        if flow.state.degraded:
            result.messages.append("The story stumbled and was steadied. Your world is untouched.")
        return result

    except Exception as exc:  # ultimate boundary: roll back and keep the player playing
        err = log_exception(exc, "flow.process_player_action", level="error")
        rolled = state_manager.restore(game, snapshot)
        game.__dict__.update(rolled.__dict__)
        result.ok = False
        result.errors.append(err.user_message)
        result.scene = _safe_scene(game)
        return result


def recommend(game: GameState) -> int:
    from core.player_model import recommend_difficulty

    return recommend_difficulty(game.player, game.learning)


def _puzzle_followups(game: GameState, solved: bool):
    from models.story import SceneAction

    if solved:
        return [
            SceneAction(action_id="read_journal", label="Read what the Unwritten Journal has recorded", kind="rest"),
            SceneAction(action_id="continue_quest", label="Continue toward the silent water", kind="explore"),
        ]
    return [
        SceneAction(action_id="try_again", label="Try the challenge once more", kind="puzzle",
                    concept=game.learning.active_concept),
        SceneAction(action_id="ask_for_hint", label="Ask the world for a gentler hint", kind="rest"),
        SceneAction(action_id="walk_away", label="Leave the challenge for now", kind="explore"),
    ]


def _merge_followups(scene, followups):
    ids = {action.action_id for action in scene.actions}
    merged = list(scene.actions) + [action for action in followups if action.action_id not in ids]
    scene.actions = merged[:5]
    return scene


def _safe_scene(game: GameState):
    from agents.continuity_safety_agent import safe_scene

    return safe_scene(game)


def _persist(game: GameState) -> None:
    try:
        from database.storage import get_storage

        get_storage().save_game(game)
    except Exception:
        pass
