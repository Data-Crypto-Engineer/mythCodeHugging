"""MythCode — Streamlit entry point.

Run locally from the REPOSITORY ROOT (Streamlit Cloud runs here too, so relative
paths behave identically):
    streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="MythCode",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui import screens, theme  # noqa: E402  (after set_page_config)

ROLES = ["Wanderer", "Inventor", "Lorekeeper", "Beast-Speaker", "Clockmender", "Wayfarer"]


def _boot() -> None:
    from utils.config import get_settings
    from database.storage import get_storage

    settings = get_settings()
    storage = get_storage()
    st.session_state.setdefault("screen", "welcome")
    st.session_state.setdefault("state", None)
    st.session_state.setdefault("turn_result", None)
    st.session_state.setdefault("scene_image", None)
    st.session_state.setdefault("pending_puzzle", None)
    st.session_state.setdefault("settings", settings)
    st.session_state.setdefault("storage", storage)


def _load_latest(state_holder) -> None:
    storage = st.session_state.storage
    session_id = storage.latest_session_id()
    if not session_id:
        return
    loaded = storage.load_game(session_id)
    if loaded is None:
        st.warning("Your previous save could not be read, so a new journey will be started.")
        return
    st.session_state.state = loaded
    st.session_state.screen = "adventure"


def _start_new(name: str, role: str, style: str) -> None:
    from core import game_engine

    with st.spinner("Elarion is drawing its first breath..."):
        state = game_engine.new_session(name or "Wanderer", role, style)
        state = game_engine.opening_scene(state)
    st.session_state.state = state
    st.session_state.turn_result = None
    st.session_state.scene_image = None
    st.session_state.screen = "adventure"
    st.rerun()


def _do_action(action: dict) -> None:
    from core import game_engine

    state = st.session_state.state
    if action.get("action_id") == "_continue":
        st.session_state.screen = "adventure"
        st.rerun()
        return

    if action.get("action_id") == "read_journal":
        st.session_state.screen = "learning"
        st.rerun()
        return
    if action.get("action_id") == "ask_for_hint":
        from agents import logic_learning_agent

        hint = logic_learning_agent.hint(state)
        st.session_state.turn_result = _hint_result(hint)
        st.rerun()
        return
    if action.get("action_id") == "try_again":
        st.session_state.screen = "adventure"
        st.session_state.turn_result = None
        st.rerun()
        return

    if action.get("kind") == "puzzle" and action.get("concept"):
        _offer_puzzle(action["concept"])
        return

    with st.spinner("The world is answering..."):
        result = game_engine.act(state, action["action_id"])
    st.session_state.turn_result = result
    _maybe_illustrate(state, result)
    st.rerun()


def _offer_puzzle(concept: str) -> None:
    from core.learning_engine import concept_unlocked, get_puzzle_prompt

    state = st.session_state.state
    if not concept_unlocked(state.learning, concept):
        st.session_state.turn_result = _note_result(
            "That idea is not ready for you yet — the world has something simpler to show you first."
        )
        st.rerun()
        return
    from agents import logic_learning_agent

    prompt = get_puzzle_prompt(state.learning, concept)
    frame = logic_learning_agent.frame_challenge(state, concept)
    prompt.framing = f"{frame.intro} {frame.flavour}".strip()
    st.session_state.pending_puzzle = prompt
    st.session_state.screen = "puzzle"
    st.rerun()


def _maybe_illustrate(state, result) -> None:
    if not (result and result.scene):
        return
    from utils.config import get_settings

    if not get_settings().has_cloudflare:
        st.session_state.scene_image = None
        return
    from agents.image_weaver import generate_scene_image

    with st.spinner("Painting the scene..."):
        st.session_state.scene_image = generate_scene_image(
            result.scene.title, result.scene.description, state.world.current_location
        )


def _hint_result(hint):
    from models.game import TurnResult
    from models.story import Scene

    scene = st.session_state.state.last_scene
    return TurnResult(
        scene=scene,
        messages=[f"✦ {hint.hint}", f"◈ {hint.nudge}"],
        debug=["hint delivered"],
    )


def _note_result(text: str):
    from models.game import TurnResult

    return TurnResult(scene=st.session_state.state.last_scene, messages=[text])


def _sidebar() -> str:
    state = st.session_state.state
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center;font-family:Cinzel,serif;letter-spacing:.2em;'
            'font-size:1.1rem;color:#3F5B44;">MYTHCODE</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="mc-mono" style="text-align:center">every choice teaches something</div>',
            unsafe_allow_html=True,
        )
        st.divider()
        if state is None:
            st.caption("Begin an adventure to open a journal.")
            return "welcome"

        from ui import components

        components.world_panel(state)
        st.divider()
        choice = st.radio(
            "Journal",
            ["Adventure", "Quest Journal", "The Unwritten Journal", "Invention Workshop", "Settings"],
            label_visibility="collapsed",
        )
        st.divider()
        confirm = st.checkbox("I understand this erases my journey", key="confirm_reset")
        if st.button("⚠ Begin completely anew", disabled=not confirm, use_container_width=True):
            st.session_state.storage.purge_all()
            st.session_state.state = None
            st.session_state.turn_result = None
            st.session_state.screen = "welcome"
            st.rerun()
        return choice


def _puzzle_screen() -> None:
    from core.learning_engine import get_puzzle_prompt, validate_puzzle
    from ui import components

    state = st.session_state.state
    prompt = st.session_state.pending_puzzle
    if prompt is None:
        st.session_state.screen = "adventure"
        st.rerun()
        return

    theme.hero("The World Is Asking", prompt.instructions)
    components.puzzle_panel(prompt)
    submission: dict = {}
    hints_used = int(st.session_state.get("puzzle_hints", 0))

    if prompt.concept in {"sequence", "loops"}:
        if prompt.concept == "sequence":
            st.markdown('<div class="mc-mono">Compose the guardian\'s commands in order.</div>', unsafe_allow_html=True)
            op_labels = {"forward": "⟶ Forward", "turn_left": "↰ Turn left", "turn_right": "↱ Turn right"}
            ops: list[str] = []
            columns = st.columns(3)
            for op, label in op_labels.items():
                with columns[list(op_labels).index(op)]:
                    count = st.number_input(label, 0, 8, 0, key=f"op_{op}")
                ops.extend([op] * int(count))
            if len(ops) > prompt.max_ops:
                st.warning(f"That is {len(ops)} commands, but the scroll holds only {prompt.max_ops}.")
            submission = {"ops": ops}
        else:
            st.markdown('<div class="mc-mono">Repeat instead of repeating yourself.</div>', unsafe_allow_html=True)
            inner = st.selectbox("Repeating action", ["forward", "turn_right", "turn_left"], key="loop_inner")
            times = st.number_input("How many times?", 1, 12, 1, key="loop_times")
            submission = {"blocks": [{"op": "repeat", "inner": inner, "times": int(times)}]}
            st.caption(f"Blocks used: 1 of {prompt.max_blocks}")

    elif prompt.concept == "conditions":
        st.markdown('<div class="mc-mono">Write ONE rule the door-keeper can follow.</div>', unsafe_allow_html=True)
        facts = prompt.spec.get("facts", ["has_key"])
        actions = prompt.spec.get("actions", ["open_door", "search_for_key"])
        condition = st.selectbox("When this is true…", facts, key="cond_fact")
        then = st.selectbox("…do this", actions, key="cond_then")
        otherwise = st.selectbox("…otherwise do this", actions, index=min(1, len(actions) - 1), key="cond_else")
        submission = {"condition": condition, "then": then, "else": otherwise}
        st.markdown(
            f'<div class="mc-python">if {condition}:\n    {then}\nelse:\n    {otherwise}</div>',
            unsafe_allow_html=True,
        )

    elif prompt.concept == "code_assembly":
        pool = prompt.spec.get("pool", [])
        options = {line["id"]: line["code"] for line in pool}
        chosen = st.multiselect(
            "Choose the lines of the spell, in order",
            options=list(options),
            format_func=lambda key: options[key],
            key="assembly_lines",
        )
        submission = {"lines": chosen}
        for line_id in chosen:
            st.markdown(f'<div class="mc-python">{options[line_id]}</div>', unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("✦ Attempt the challenge", use_container_width=True):
            st.session_state.puzzle_hints = hints_used
            from core import game_engine

            with st.spinner("The world is testing your rule..."):
                result = game_engine.act(state, "_challenge", submission)
            if result.reveal is None and result.puzzle_result and not result.puzzle_result.startswith("Solved"):
                # still unsolved: stay in the workshop with feedback
                st.session_state.turn_result = result
                st.session_state.pending_puzzle = get_puzzle_prompt(state.learning, prompt.concept)
                st.rerun()
            else:
                st.session_state.turn_result = result
                st.session_state.pending_puzzle = None
                st.session_state.screen = "adventure"
                _maybe_illustrate(state, result)
                st.rerun()
    with col_b:
        if st.button("◈ Ask for a gentler hint", use_container_width=True):
            from agents import logic_learning_agent

            hint = logic_learning_agent.hint(state, prompt.concept)
            st.session_state.puzzle_hints = hints_used + 1
            st.session_state.turn_result = _hint_result(hint)
            st.rerun()
    with col_c:
        if st.button("← Leave the challenge", use_container_width=True):
            st.session_state.pending_puzzle = None
            st.session_state.screen = "adventure"
            st.rerun()

    last = st.session_state.get("turn_result")
    if last:
        for message in last.messages:
            st.info(message)
        if last.puzzle_result and prompt.concept == "sequence" and last.scene:
            st.markdown(f'<div class="mc-mono">{last.puzzle_result}</div>', unsafe_allow_html=True)


def main() -> None:
    _boot()
    theme.apply()
    state = st.session_state.state
    storage = st.session_state.storage
    has_save = storage.latest_session_id() is not None

    choice = _sidebar()

    if choice == "welcome" and st.session_state.screen == "welcome":
        action = screens.welcome_screen(has_save)
        if action and action.get("action") == "_continue":
            _load_latest(state)
        elif action:
            st.session_state.screen = "create"
            st.rerun()
        return

    if st.session_state.screen == "create":
        action = screens.creation_screen()
        if action and action.get("kind") == "new":
            _start_new(action["name"], action["role"], action["style"])
        return

    if st.session_state.state is None:
        st.session_state.screen = "welcome"
        st.rerun()
        return

    state = st.session_state.state

    if st.session_state.screen == "puzzle":
        _puzzle_screen()
        return

    if st.session_state.screen == "learning" or choice == "The Unwritten Journal":
        st.session_state.screen = "learning"
        screens.learning_journal(state)
        if st.button("← Back to the adventure"):
            st.session_state.screen = "adventure"
            st.rerun()
        return

    if choice == "Quest Journal":
        screens.quest_journal(state)
        return

    if choice == "Invention Workshop":
        action = screens.invention_lab(state)
        if action:
            from core import game_engine

            effect = game_engine.craft_invention(state, action["name"], action["blocks"])
            st.success(effect)
        return

    if choice == "Settings":
        screens.settings_panel(
            st.session_state.settings.diagnostics(), getattr(st.session_state.storage, "degraded", False)
        )
        return

    # default: the adventure itself
    st.session_state.screen = "adventure"
    theme.hero(
        f"{state.world.current_location}",
        f"{state.player.name} the {state.player.role} · {state.quest.title}",
    )
    action = screens.adventure_screen(state)
    if action:
        _do_action(action)


main()
