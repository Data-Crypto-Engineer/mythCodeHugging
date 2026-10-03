"""Reusable, presentation-only components. No business logic, no API calls."""
from __future__ import annotations

from typing import Any

import streamlit as st

from models.game import GameState
from models.learning import PuzzlePrompt, PuzzleResult
from models.story import Scene
from ui import theme


def scene_card(scene: Scene, image_uri: str | None = None) -> None:
    if image_uri:
        st.markdown(
            f'<div class="mc-card" style="padding:.6rem">'
            f'<img src="{image_uri}" alt="Scene illustration" '
            f'style="width:100%;border-radius:14px;display:block;"/></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<div class="mc-card"><div class="mc-scene-title">{scene.title}</div>'
        f'<div class="mc-scene-body">{scene.description}</div></div>',
        unsafe_allow_html=True,
    )
    for line in scene.dialogue:
        st.markdown(
            f'<div class="mc-dialogue"><div class="mc-speaker">{line.speaker}</div>'
            f'<div class="mc-line">“{line.text}”</div></div>',
            unsafe_allow_html=True,
        )
    if scene.consequence_preview:
        st.markdown(
            f'<div class="mc-mono">◈ {scene.consequence_preview}</div>', unsafe_allow_html=True
        )


def world_panel(state: GameState) -> None:
    world = state.world
    st.markdown(
        theme.pill(f"⟡ {world.current_location}", "lav")
        + theme.pill(f"⚑ {world.kingdom}", "blue")
        + theme.pill(f"◆ turn {state.turn}", "gold"),
        unsafe_allow_html=True,
    )
    theme.meter("Village morale", world.village_morale, 100, "/100")
    theme.meter("Kingdom energy", world.energy_reserve, 100, "/100")
    spirit = world.forest_spirit_trust
    theme.meter("Spirit trust", spirit, 100)
    guardian_labels = {
        "inactive": "Dormant", "stirring": "Stirring", "active": "Awake", "awakened": "Awakened"
    }
    st.markdown(
        theme.pill(f"Guardian: {guardian_labels.get(world.clockwork_guardian, 'unknown')}", "gold")
        + theme.pill(f"Water: {world.water_supply}", "blue"),
        unsafe_allow_html=True,
    )
    if world.unresolved_conflicts:
        st.markdown('<div class="mc-mono">Open threads</div>', unsafe_allow_html=True)
        for conflict in world.unresolved_conflicts[-3:]:
            st.markdown(f'<div class="mc-journal-entry">{conflict}</div>', unsafe_allow_html=True)


def grid_preview(spec: dict[str, Any], trace: dict[str, Any] | None = None) -> None:
    """Renders the guardian's room as a CSS grid — the 'game' part of the game."""
    grid = spec.get("grid", {})
    width, height = int(grid.get("w", 0)), int(grid.get("h", 0))
    if not width or not height:
        return
    walls = {tuple(wall) for wall in grid.get("walls", [])}
    goal = tuple(grid.get("goal", []))
    trail = {tuple(step) for step in (trace or {}).get("path", [])}
    here = tuple((trace or {}).get("position", []))

    cells = []
    for y in range(height):
        for x in range(width):
            classes = ["mc-cell"]
            glyph = ""
            if (x, y) in walls:
                classes.append("wall")
            if (x, y) == goal:
                classes.append("goal")
                glyph = "◎"
            if (x, y) in trail:
                classes.append("trail")
            if (x, y) == here and trace:
                classes.append("here")
                glyph = "▲"
            if not glyph and grid.get("start") and (x, y) == (grid["start"]["x"], grid["start"]["y"]):
                glyph = "✦"
            cells.append(f'<div class="{" ".join(classes)}">{glyph}</div>')

    st.markdown(
        f'<div class="mc-map" style="grid-template-columns: repeat({width}, 30px)">'
        + "".join(cells)
        + "</div>",
        unsafe_allow_html=True,
    )


def puzzle_panel(prompt: PuzzlePrompt, result: PuzzleResult | None = None) -> None:
    st.markdown(
        f'<div class="mc-card"><div class="mc-scene-title">{prompt.title}</div>'
        f'<div class="mc-scene-body">{prompt.framing or prompt.instructions}</div>'
        f'<div class="mc-mono">Difficulty {prompt.difficulty} · '
        f'{"max " + str(prompt.max_ops) + " commands" if prompt.max_ops else "max " + str(prompt.max_blocks) + " blocks"}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    if prompt.concept == "sequence":
        grid_preview(prompt.spec, (result.trace if result else None))


def reveal_card(reveal) -> None:
    st.markdown(
        f'<div class="mc-reveal"><h4>✦ The Unwritten Journal records: {reveal.title}</h4>'
        f'<div class="mc-scene-body">{reveal.explanation}</div>'
        f'<div class="mc-mono">In the world: {reveal.world_analogy}</div>'
        f'<div class="mc-python">{reveal.python_example}</div></div>',
        unsafe_allow_html=True,
    )
