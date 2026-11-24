
"""CrewAI Flow orchestration — the only entry point the UI calls.

The Flow coordinates specialist agents while keeping GameState as the
single source of truth.

A turn follows this sequence:
    player action
        -> Director / challenge preparation
        -> Player Insight
        -> Story Weaver
        -> World Keeper
        -> Safety review
        -> validated state commit
        -> persistence

Important design rules:
- Agents propose; deterministic validators decide what can be applied.
- World and NPC-memory changes are committed only after safety approval.
- A failed turn is rolled back to its original snapshot.
- Puzzle answers are evaluated deterministically, not executed as code.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.game import GameState, TurnResult
from models.story import Scene, SceneAction
from utils.logger import get_logger

logger = get_logger("flow")


class TurnState(BaseModel):
    """Temporary working state for one Flow execution.

    This is deliberately separate from the persistent GameState.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    game: GameState

    action_id: str = ""
    action_label: str = "The player hesitates"
    action_kind: str = "explore"
    requested_concept: str = ""

    context_block: str = ""

    plan: Any = None
    scene: Any = None
    game_patch: Any = None

    changes: list[Any] = Field(default_factory=list)
    memory_notes: list[Any] = Field(default_factory=list)

    safety: Any = None
    reveal: Any = None
    puzzle_prompt: Any = None
    puzzle_result: Any = None

    submission: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    degraded: bool = False


def _find_action(game: GameState, action_id: str) -> SceneAction:
    """Find an action in the last scene or create a safe fallback."""

    if game.last_scene:
        for action in game.last_scene.actions:
            if action.action_id == action_id:
                return action

    return SceneAction(
        action_id=action_id or "unknown",
        label=action_id.replace("_", " ") or "Act",
        kind="explore",
    )


def _difficulty(game: GameState) -> int:
    """Calculate the next recommended challenge difficulty."""

    from core.player_model import recommend_difficulty

    return recommend_difficulty(game.player, game.learning)


def _build_flow() -> Any:
    """Build the Flow lazily so importing this module does not require CrewAI."""

    from crewai.flow.flow import Flow, listen, or_, router, start

    from agents import continuity_safety_agent as safety_agent
    from agents import director_agent
    from agents import logic_learning_agent
    from agents import player_insight_agent
    from agents import story_weaver_agent
    from agents import world_keeper_agent

    from core import learning_engine
    from core import state_manager, state_validator

    class MythCodeFlow(Flow[TurnState]):
        """Process one player action from interpretation to persistence."""

        # ---------------------------------------------------------
        # 1. Interpret the player's action
        # ---------------------------------------------------------

        @start()
        def open_turn(self):
            action = _find_action(
                self.state.game,
                self.state.action_id,
            )

            self.state.action_label = action.label
            self.state.action_kind = action.kind
            self.state.requested_concept = action.concept or ""

            self.state.context_block = state_manager.summary_of(
                self.state.game
            )

            self.state.notes.append(
                f"Action '{action.label}' classified as {action.kind}."
            )

        # ---------------------------------------------------------
        # 2. Choose the normal story or challenge path
        # ---------------------------------------------------------

        @router(open_turn)
        def route_action(self):
            if (
                self.state.action_kind == "puzzle"
                or self.state.requested_concept
            ):
                return "challenge"

            return "normal"

        # ---------------------------------------------------------
        # 3A. Normal narrative path
        # ---------------------------------------------------------

        @listen("normal")
        def direct_turn(self):
            self.state.plan = director_agent.plan_turn(
                self.state.game,
                self.state.action_label,
                self.state.action_kind,
                self.state.context_block,
            )

            self.state.notes.append(
                "Director selected category "
                f"'{self.state.plan.event_category}'."
            )

        # ---------------------------------------------------------
        # 3B. Challenge preparation path
        # ---------------------------------------------------------

        @listen("challenge")
        def prepare_challenge(self):
            from core.learning_engine import (
                concept_unlocked,
                next_concept,
            )

            concept = (
                self.state.requested_concept
                or next_concept(self.state.game.learning)
            )

            if not concept_unlocked(
                self.state.game.learning,
                concept,
            ):
                self.state.notes.append(
                    f"Concept '{concept}' is locked; "
                    "using the normal story path instead."
                )
                concept = "none"

            plan = director_agent.offline_plan(
                self.state.game,
                self.state.action_label,
                "puzzle",
            )

            if concept != "none":
                plan.suggested_challenge = concept
                plan.event_category = "puzzle"
                plan.required_agents = [
                    "story",
                    "world",
                    "learning",
                ]

            self.state.plan = plan

            self.state.notes.append(
                f"Challenge prepared for concept '{concept}'."
            )

        # ---------------------------------------------------------
        # 4. Update the player model
        # ---------------------------------------------------------

        @listen(or_("direct_turn", "prepare_challenge"))
        def adapt_player(self):
            player_insight_agent.update_profile(
                self.state.game,
                self.state.action_label,
                self.state.action_kind,
                "in progress",
            )

        # ---------------------------------------------------------
        # 5. Generate the narrative and optional challenge
        # ---------------------------------------------------------

        @listen(adapt_player)
        def tell_story(self):
            challenge = self.state.plan.suggested_challenge

            if challenge != "none":
                frame = logic_learning_agent.frame_challenge(
                    self.state.game,
                    challenge,
                )

                self.state.puzzle_prompt = (
                    learning_engine.get_puzzle_prompt(
                        self.state.game.learning,
                        challenge,
                    )
                )

                self.state.puzzle_prompt.framing = (
                    f"{frame.intro} {frame.flavour}"
                ).strip()

            self.state.scene = story_weaver_agent.weave(
                self.state.game,
                self.state.plan,
                self.state.action_label,
            )

        # ---------------------------------------------------------
        # 6. Ask the World Keeper for proposed changes
        # ---------------------------------------------------------

        @listen(tell_story)
        def keep_world(self):
            patch = world_keeper_agent.propose(
                self.state.game,
                self.state.scene,
                self.state.action_label,
            )

            if patch is None:
                patch = world_keeper_agent.offline_patch(
                    self.state.game,
                    self.state.scene,
                    self.state.action_label,
                )

            self.state.game_patch = patch

            # Validate proposed world changes, but do not apply them yet.
            accepted, rejected = state_validator.validate_changes(
                self.state.game,
                patch.changes,
            )

            self.state.changes = accepted

            # Keep memory proposals temporary until safety approval.
            # This prevents rejected scenes from changing NPC memories.
            self.state.memory_notes = list(
                patch.memory_notes or []
            )

            self.state.notes.extend(rejected)

        # ---------------------------------------------------------
        # 7. Safety review
        # ---------------------------------------------------------

        @listen(keep_world)
        def guard(self):
            verdict = safety_agent.review(
                self.state.game,
                self.state.scene,
                self.state.changes,
                self.state.plan,
            )

            self.state.safety = verdict

        @router(guard)
        def decide(self):
            if not self.state.safety.approved:
                return "blocked"

            return "approved"

        # ---------------------------------------------------------
        # 7A. Safe fallback after a rejected scene
        # ---------------------------------------------------------

        @listen("blocked")
        def rescue(self):
            self.state.scene = safety_agent.safe_scene(
                self.state.game
            )

            # No proposed world changes or memories are committed.
            self.state.changes = []
            self.state.memory_notes = []

            # Preserve the original negative safety verdict for reporting.
            self.state.degraded = True

            self.state.notes.append(
                "Safety veto — served the predefined safe scene; "
                "proposed world changes were discarded."
            )

        # ---------------------------------------------------------
        # 8. Commit validated changes
        # ---------------------------------------------------------

        @listen(or_("approved", rescue))
        def commit(self):
            game = self.state.game

            # Apply only changes accepted by the deterministic validator.
            applied = state_validator.apply_changes(
                game,
                self.state.changes,
            )

            # NPC memories are committed only after safety approval.
            for note in self.state.memory_notes:
                state_manager.remember(
                    game,
                    note.npc_id,
                    note.note,
                )

            state_manager.add_ledger(
                game,
                (
                    f"{self.state.action_label} → "
                    f"{', '.join(applied) or 'no world change'}"
                ),
            )

            state_manager.append_history(
                game,
                (
                    f"{self.state.scene.title}: "
                    f"{self.state.scene.description[:120]}"
                ),
            )

            state_manager.fold_history(game)

            game.turn += 1
            game.last_scene = self.state.scene

            game.learning.next_difficulty = _difficulty(game)

            state_manager.validate_and_report(game)

            # Mark a newly introduced challenge for the learning system.
            if (
                self.state.plan.suggested_challenge != "none"
                and self.state.puzzle_prompt is not None
            ):
                record = game.learning.record(
                    self.state.puzzle_prompt.concept
                )

                record.introduced = True

                # The explanation is shown only after a correct answer.
                self.state.reveal = None

        # ---------------------------------------------------------
        # 9. Persist the completed turn
        # ---------------------------------------------------------

        @listen(commit)
        def finish(self):
            try:
                from database.storage import get_storage

                storage = get_storage()

                storage.save_game(self.state.game)

                storage.log_turn(
                    self.state.game.session_id,
                    self.state.game.turn,
                    self.state.action_kind,
                    (
                        f"{self.state.scene.title}: "
                        f"{self.state.action_label}"
                    ),
                )

            except Exception as exc:
                # Persistence failure must not destroy an otherwise
                # successfully generated turn.
                logger.exception(
                    "Could not persist completed turn: %s",
                    exc,
                )

                self.state.notes.append(
                    f"Save skipped: {type(exc).__name__}"
                )

    return MythCodeFlow


def process_player_action(
    game: GameState,
    action_id: str,
    submission: dict[str, Any] | None = None,
) -> TurnResult:
    """Application-facing entry point.

    Never exposes an unhandled exception to the UI.
    Restores the original game state if a turn fails.
    """

    from core import learning_engine
    from core import state_manager, state_validator
    from utils.error_handler import log_exception

    result = TurnResult()

    snapshot = state_manager.snapshot(game)

    try:
        state_validator.validate_state(game)

        # ---------------------------------------------------------
        # Puzzle submissions are evaluated deterministically.
        # No agent is needed to decide whether an answer is correct.
        # ---------------------------------------------------------

        if submission:
            prompt = learning_engine.get_puzzle_prompt(
                game.learning,
                game.learning.active_concept,
            )

            verdict = learning_engine.validate_puzzle(
                prompt.concept,
                prompt.spec,
                submission,
            )

            hints = int(
                submission.get("hints_used", 0) or 0
            )

            learning_engine.record_attempt(
                game.learning,
                prompt.concept,
                verdict,
                hints,
                prompt.difficulty,
            )

            from core.player_model import mastery_after

            mastery_after(
                game.player,
                prompt.concept,
                verdict.solved,
                game.learning.record(prompt.concept).attempts == 1,
                hints,
            )

            game.learning.next_difficulty = recommend(game)

            result.puzzle_result = (
                f"{'Solved' if verdict.solved else 'Not yet'}: "
                f"{verdict.reason}"
            )

            state_manager.append_history(
                game,
                (
                    f"Challenge attempt ({prompt.concept}): "
                    f"{verdict.reason[:90]}"
                ),
            )

            if verdict.solved:
                result.reveal = learning_engine.concept_reveal(
                    prompt.concept
                )

                game.turn += 1

            state_manager.validate_and_report(game)
            _persist(game)

            result.scene = game.last_scene or Scene(
                title="The Scroll Records Your Answer",
                description=verdict.reason,
                actions=_puzzle_followups(
                    game,
                    verdict.solved,
                ),
                category="consequence",
                location=game.world.current_location,
            )

            result.scene = _merge_followups(
                result.scene,
                _puzzle_followups(game, verdict.solved),
            )

            return result

        # ---------------------------------------------------------
        # Normal player action: run the CrewAI Flow.
        # ---------------------------------------------------------

        FlowClass = _build_flow()

        flow = FlowClass()

        flow.state.game = game
        flow.state.action_id = action_id or ""

        flow.kickoff()

        result.scene = flow.state.scene
        result.puzzle = flow.state.puzzle_prompt
        result.reveal = flow.state.reveal
        result.safety = flow.state.safety
        result.debug = flow.state.notes

        result.state_changed = bool(
            flow.state.changes
        )

        if flow.state.degraded:
            result.messages.append(
                "The story stumbled and was steadied. "
                "Your world changes were not applied."
            )

        return result

    except Exception as exc:
        err = log_exception(
            exc,
            "flow.process_player_action",
            level="error",
        )

        # Restore the original state after any failed operation.
        rolled = state_manager.restore(game, snapshot)

        game.__dict__.update(rolled.__dict__)

        result.ok = False
        result.errors.append(err.user_message)
        result.scene = _safe_scene(game)

        return result


def recommend(game: GameState) -> int:
    """Return the next recommended puzzle difficulty."""

    from core.player_model import recommend_difficulty

    return recommend_difficulty(
        game.player,
        game.learning,
    )


def _puzzle_followups(
    game: GameState,
    solved: bool,
) -> list[SceneAction]:
    """Return appropriate actions after a puzzle attempt."""

    if solved:
        return [
            SceneAction(
                action_id="read_journal",
                label="Read what the Unwritten Journal has recorded",
                kind="rest",
            ),
            SceneAction(
                action_id="continue_quest",
                label="Continue toward the silent water",
                kind="explore",
            ),
        ]

    return [
        SceneAction(
            action_id="try_again",
            label="Try the challenge once more",
            kind="puzzle",
            concept=game.learning.active_concept,
        ),
        SceneAction(
            action_id="ask_for_hint",
            label="Ask the world for a gentler hint",
            kind="rest",
        ),
        SceneAction(
            action_id="walk_away",
            label="Leave the challenge for now",
            kind="explore",
        ),
    ]


def _merge_followups(
    scene: Scene,
    followups: list[SceneAction],
) -> Scene:
    """Add missing follow-up actions without duplicating existing ones."""

    existing_ids = {
        action.action_id
        for action in scene.actions
    }

    merged = list(scene.actions) + [
        action
        for action in followups
        if action.action_id not in existing_ids
    ]

    scene.actions = merged[:5]

    return scene


def _safe_scene(game: GameState) -> Scene:
    """Return a predefined safe scene if normal processing fails."""

    from agents.continuity_safety_agent import safe_scene

    return safe_scene(game)


def _persist(game: GameState) -> None:
    """Best-effort persistence for puzzle progress."""

    try:
        from database.storage import get_storage

        get_storage().save_game(game)

    except Exception as exc:
        logger.exception(
            "Could not persist game state: %s",
            exc,
        )
