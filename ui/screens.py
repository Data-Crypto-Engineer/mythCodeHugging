"""Screens. Each function renders and returns an optional action dict."""
from __future__ import annotations

import streamlit as st

from models.game import GameState
from ui import components, theme


def welcome_screen(has_save: bool) -> dict | None:
    theme.hero("MYTHCODE", "An adaptive fantasy world where every choice teaches you something.")
    st.markdown(
        '<div class="mc-card"><div class="mc-scene-body">'
        "The river that turned Whispering Village's wheel has gone quiet. Elarion does not explain "
        "itself; it builds rooms, doors and rivers, and waits to see whether you can find the rule "
        "inside the world. You will learn to write those rules — first as magic, then as Python."
        "</div>"
        '<div class="mc-mono">Your choices shape the world. Your world shapes your mind.</div></div>',
        unsafe_allow_html=True,
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✦ Begin a new adventure", use_container_width=True):
            return {"screen": "create"}
    with col_b:
        if has_save and st.button("↺ Continue your adventure", use_container_width=True):
            return {"screen": "adventure", "action": "_continue"}
    if not has_save:
        st.caption("No saved journey found yet — begin a new adventure to create one.")
    return None


def creation_screen() -> dict | None:
    theme.hero("Choose Your Wanderer", "Your role changes how the world greets you — never how well you can learn.")
    with st.form("creation"):
        name = st.text_input("What shall the world call you?", max_chars=24, placeholder="e.g. Wren")
        role = st.selectbox(
            "Preferred fantasy role",
            ["Wanderer", "Inventor", "Lorekeeper", "Beast-Speaker", "Clockmender", "Wayfarer"],
            help="This shapes dialogue and story flavour. It has no effect on difficulty or learning.",
        )
        style = st.selectbox(
            "How do you like to explore?",
            ["Curious", "Careful", "Bold", "Patient"],
            help="Optional. The world adapts as it watches you, whatever you choose here.",
        )
        submitted = st.form_submit_button("Step into Elarion", use_container_width=True)
    if submitted:
        return {"screen": "adventure", "kind": "new", "name": name, "role": role, "style": style}
    return None


def action_buttons(scene, puzzles_enabled: bool) -> dict | None:
    """The player's choices. Every choice is a real button — no typing needed."""
    st.markdown('<div class="mc-mono">What do you do?</div>', unsafe_allow_html=True)
    for index, action in enumerate(scene.actions):
        label = action.label
        if action.kind == "puzzle":
            label = f"◆ {label}"
        if st.button(label, key=f"act_{action.action_id}_{index}", use_container_width=True):
            return {"action_id": action.action_id, "kind": action.kind, "concept": action.concept}
    return None


def adventure_screen(state: GameState) -> dict | None:
    result = st.session_state.get("turn_result")
    image_uri = st.session_state.get("scene_image")

    if state.last_scene:
        components.scene_card(state.last_scene, image_uri)

    if result and result.reveal:
        components.reveal_card(result.reveal)

    if result and result.puzzle:
        components.puzzle_panel(result.puzzle)

    if result and result.puzzle_result:
        tone = "gold" if result.puzzle_result.startswith("Solved") else "lav"
        st.markdown(theme.pill(result.puzzle_result, tone), unsafe_allow_html=True)

    for message in (result.messages if result else []):
        st.info(message)
    for error in (result.errors if result else []):
        st.warning(error)

    if state.last_scene:
        return action_buttons(state.last_scene, puzzles_enabled=True)
    return None


def quest_journal(state: GameState) -> None:
    st.markdown(f"### ⚑ {state.quest.title}")
    st.markdown(f'<div class="mc-scene-body">{state.quest.objective}</div>', unsafe_allow_html=True)
    st.markdown(
        theme.pill(f"stage {state.quest.stage}", "lav")
        + theme.pill(f"location {state.quest.location or 'unknown'}", "blue")
        + (theme.pill(f"road: {state.quest.path}", "gold") if state.quest.path else ""),
        unsafe_allow_html=True,
    )
    if state.world.completed_quests:
        st.markdown("#### Completed")
        for quest_id in state.world.completed_quests:
            st.markdown(f'<div class="mc-journal-entry">✓ {quest_id.replace("_", " ")}</div>', unsafe_allow_html=True)
    if state.ledger:
        st.markdown("#### The Chronicle (important choices)")
        for entry in reversed(state.ledger[-14:]):
            st.markdown(f'<div class="mc-journal-entry">◆ {entry}</div>', unsafe_allow_html=True)
    if state.world.discovered_locations:
        st.markdown("#### Discovered places")
        st.markdown(
            "".join(theme.pill(place, "sage") for place in state.world.discovered_locations),
            unsafe_allow_html=True,
        )
    if state.world.unresolved_conflicts:
        st.markdown("#### Unresolved")
        for conflict in state.world.unresolved_conflicts:
            st.markdown(f'<div class="mc-journal-entry">… {conflict}</div>', unsafe_allow_html=True)


def learning_journal(state: GameState) -> None:
    st.markdown("### ✦ The Unwritten Journal")
    st.caption(
        "Every entry below comes from a challenge you actually solved — never from narration."
    )
    learning = state.learning
    for concept in ("sequence", "conditions", "loops", "code_assembly"):
        record = learning.records.get(concept)
        mastery = state.player.concept_mastery.for_concept(concept)
        if record is None or not record.introduced:
            st.markdown(f'<div class="mc-mono">◇ {concept.replace("_", " ")} — not yet encountered</div>', unsafe_allow_html=True)
            continue
        status = "solved" if record.successes else "attempted"
        st.markdown(
            theme.pill(f"{concept.replace('_', ' ')} · {status}", "gold" if record.successes else "lav")
            + theme.pill(f"attempts {record.attempts}")
            + theme.pill(f"hints {record.hints_used}")
            + theme.pill(f"mastery {mastery:.0%}", "blue"),
            unsafe_allow_html=True,
        )
        theme.meter("Understanding", int(mastery * 100), 100, "%")
        if record.revealed:
            from core.learning_engine import concept_reveal

            components.reveal_card(concept_reveal(concept))

    if state.inventions:
        st.markdown("#### Your inventions")
        for invention in state.inventions:
            st.markdown(
                f'<div class="mc-journal-entry">✧ <b>{invention.name}</b> — {invention.effect}</div>',
                unsafe_allow_html=True,
            )


def invention_lab(state: GameState) -> dict | None:
    st.markdown("### ✧ Invention Workshop")
    st.caption(
        "Blocks, not code. Every device you build is composed of the same four ideas you have met in the world."
    )
    name = st.text_input("Name your device", max_chars=40, placeholder="e.g. The Tireless Lantern")
    blocks: list[dict] = []
    for index in range(3):
        col_a, col_b, col_c = st.columns([2, 1, 2])
        with col_a:
            kind = st.selectbox(
                f"Block {index + 1}",
                ["none", "move", "turn_left", "turn_right", "repeat", "if", "glow"],
                key=f"blk_kind_{index}",
            )
        with col_b:
            times = st.number_input("×", 1, 10, 1, key=f"blk_times_{index}")
        with col_c:
            detail = st.text_input(
                "target / condition", key=f"blk_detail_{index}",
                placeholder="forward, or has_key", label_visibility="collapsed",
            )
        if kind == "none":
            continue
        blocks.append({"kind": kind if kind != "repeat" else "repeat", "times": int(times),
                       "condition": detail if kind == "if" else "",
                       "inner": detail if kind == "repeat" else ""})
    if st.button("⟡ Craft this invention", use_container_width=True):
        if not blocks:
            st.warning("A device needs at least one block.")
        else:
            return {"name": name, "blocks": blocks}
    return None


def settings_panel(diagnostics: dict, storage_degraded: bool) -> None:
    st.markdown("### ⚙ Configuration")
    for key, value in diagnostics.items():
        st.markdown(f'<div class="mc-mono">{key}: {value}</div>', unsafe_allow_html=True)
    if diagnostics.get("mode") == "offline":
        st.info(
            "**Storyteller's Simulator (offline).** No API keys detected, so MythCode is running its "
            "deterministic director with templated scenes. Every puzzle, rule check, memory and save is "
            "fully active — only the prose and the AI hints are simplified."
        )
    if storage_degraded:
        st.warning("Storage fell back to memory. Progress will not survive a restart.")
    st.markdown(
        '<div class="mc-mono">Add GEMINI_API_KEY and GROQ_API_KEY to .streamlit/secrets.toml '
        "(locally) or App → Settings → Secrets (Community Cloud) to enable the full agent crew.</div>",
        unsafe_allow_html=True,
    )
