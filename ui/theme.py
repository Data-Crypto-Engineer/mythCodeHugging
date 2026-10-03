"""Storybook-inspired visual language.

The palette is deliberately LIGHT (warm cream, misty lavender, soft sage, muted
gold) — a lit page rather than a dark dashboard. Motion is restrained and respects
`prefers-reduced-motion`.
"""
from __future__ import annotations

import streamlit as st

PALETTE = {
    "lavender": "#7C6BA8",
    "lavender_soft": "#B7A8D6",
    "sage": "#8AA88C",
    "cream": "#FBF7EF",
    "cream_deep": "#F1EBF7",
    "gold": "#C9A227",
    "pale_blue": "#AFC7DA",
    "forest": "#3F5B44",
    "ink": "#2F2A3A",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=EB+Garamond:ital,wght@0,400;0,600;1,400&display=swap');

.stApp {
  background:
    radial-gradient(1100px 600px at 12% -8%, rgba(183,168,214,.45), transparent 60%),
    radial-gradient(900px 520px at 92% 6%, rgba(175,199,218,.42), transparent 62%),
    radial-gradient(760px 520px at 50% 108%, rgba(138,168,140,.30), transparent 62%),
    linear-gradient(180deg, #FBF7EF 0%, #F4EEFA 58%, #EEF4EC 100%);
  color: #2F2A3A;
  font-family: 'EB Garamond', Georgia, serif;
  font-size: 18px;
}

/* Floating motes — the "motion" that makes it feel like a world, not a form */
.stApp::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    radial-gradient(2.2px 2.2px at 18% 24%, rgba(201,162,39,.55), transparent),
    radial-gradient(2.6px 2.6px at 74% 16%, rgba(183,168,214,.65), transparent),
    radial-gradient(2px   2px   at 42% 72%, rgba(138,168,140,.55), transparent),
    radial-gradient(2.4px 2.4px at 88% 64%, rgba(175,199,218,.65), transparent),
    radial-gradient(1.8px 1.8px at 62% 88%, rgba(201,162,39,.45), transparent);
  animation: drift 26s linear infinite;
}
@keyframes drift {
  0%   { transform: translate3d(0,0,0) scale(1);       opacity: .85; }
  50%  { transform: translate3d(-14px,-22px,0) scale(1.04); opacity: 1; }
  100% { transform: translate3d(0,0,0) scale(1);       opacity: .85; }
}

.mc-hero {
  position: relative; z-index: 1; text-align: center; padding: 2.4rem 1rem 1.2rem;
  border-radius: 26px; margin-bottom: 1.4rem;
  background: linear-gradient(160deg, rgba(255,255,255,.72), rgba(241,235,247,.52));
  border: 1px solid rgba(124,107,168,.28);
  box-shadow: 0 18px 44px rgba(63,91,68,.13), inset 0 1px 0 rgba(255,255,255,.7);
}
.mc-title {
  font-family: 'Cinzel', serif; font-weight: 700; letter-spacing: .16em;
  font-size: clamp(2.1rem, 6vw, 3.5rem); margin: 0; line-height: 1.05;
  background: linear-gradient(96deg, #3F5B44 0%, #7C6BA8 46%, #C9A227 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 2px 12px rgba(124,107,168,.28));
}
.mc-tagline {
  font-style: italic; color: #5B5470; margin-top: .5rem;
  font-size: clamp(1rem, 2.4vw, 1.22rem); letter-spacing: .02em;
}
.mc-rule {
  height: 2px; width: 132px; margin: .9rem auto 0;
  background: linear-gradient(90deg, transparent, #C9A227, transparent);
}

.mc-card {
  position: relative; z-index: 1; border-radius: 20px; padding: 1.25rem 1.4rem;
  background: linear-gradient(178deg, rgba(255,255,255,.88), rgba(251,247,239,.78));
  border: 1px solid rgba(124,107,168,.20);
  box-shadow: 0 12px 30px rgba(63,91,68,.11);
  margin-bottom: 1rem;
  animation: rise .6s cubic-bezier(.2,.8,.25,1) both;
}
@keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }

.mc-scene-title {
  font-family: 'Cinzel', serif; font-size: 1.42rem; font-weight: 700;
  color: #3F5B44; margin-bottom: .3rem; letter-spacing: .02em;
}
.mc-scene-body { font-size: 1.09rem; line-height: 1.78; color: #33304A; }
.mc-scene-body::first-letter {
  font-family: 'Cinzel', serif; font-size: 3.1rem; line-height: .86;
  float: left; padding: .1rem .55rem 0 0; color: #7C6BA8;
}

.mc-dialogue {
  border-left: 3px solid #C9A227; background: rgba(255,255,255,.6);
  border-radius: 0 14px 14px 0; padding: .7rem 1rem; margin: .55rem 0;
  animation: rise .5s cubic-bezier(.2,.8,.25,1) both;
}
.mc-speaker {
  font-family: 'Cinzel', serif; font-size: .82rem; letter-spacing: .14em;
  text-transform: uppercase; color: #7C6BA8;
}
.mc-line { font-size: 1.05rem; font-style: italic; color: #3A3550; }

.mc-pill {
  display: inline-block; padding: .24rem .72rem; border-radius: 999px;
  font-size: .8rem; letter-spacing: .1em; text-transform: uppercase;
  font-family: 'Cinzel', serif; margin: 0 .35rem .35rem 0;
  background: rgba(138,168,140,.22); color: #3F5B44;
  border: 1px solid rgba(63,91,68,.24);
}
.mc-pill.gold  { background: rgba(201,162,39,.20); color: #7A5F12; border-color: rgba(201,162,39,.4); }
.mc-pill.lav   { background: rgba(183,168,214,.26); color: #4E4278; border-color: rgba(124,107,168,.34); }
.mc-pill.blue  { background: rgba(175,199,218,.28); color: #2F4A63; border-color: rgba(47,74,99,.24); }

.mc-reveal {
  border-radius: 18px; padding: 1.1rem 1.3rem; margin-top: .9rem;
  background: linear-gradient(140deg, rgba(63,91,68,.10), rgba(201,162,39,.12));
  border: 1px solid rgba(201,162,39,.42);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6);
}
.mc-reveal h4 { font-family: 'Cinzel', serif; color: #7A5F12; margin: 0 0 .4rem; }

.mc-python {
  background: #2B2740; color: #F3EFFA; border-radius: 12px;
  padding: .85rem 1rem; font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: .94rem; line-height: 1.6; overflow-x: auto; margin-top: .6rem;
  box-shadow: inset 0 0 0 1px rgba(183,168,214,.28);
}

.mc-map {
  display: grid; gap: 3px; background: rgba(63,91,68,.12);
  padding: 3px; border-radius: 12px; width: max-content; margin: .5rem auto;
}
.mc-cell {
  width: 30px; height: 30px; border-radius: 5px; background: #F6F3EC;
  display: flex; align-items: center; justify-content: center;
  font-size: 1rem; transition: background .25s ease;
}
.mc-cell.wall  { background: #6E6379; }
.mc-cell.goal  { background: rgba(201,162,39,.55); }
.mc-cell.trail { background: rgba(183,168,214,.55); }
.mc-cell.here  { background: #3F5B44; color: #fff; }
.mc-cell.boom  { animation: shake .4s ease; }
@keyframes shake { 25%{transform:translateX(-3px)} 75%{transform:translateX(3px)} }

.mc-meter { height: 11px; border-radius: 999px; background: rgba(124,107,168,.16); overflow: hidden; margin: .22rem 0 .8rem; }
.mc-meter > span {
  display: block; height: 100%;
  background: linear-gradient(90deg, #8AA88C, #C9A227);
  transition: width .9s cubic-bezier(.2,.8,.25,1);
}

.mc-journal-entry {
  border-left: 2px solid rgba(124,107,168,.4); padding: .35rem .85rem;
  margin-bottom: .5rem; font-size: 1rem;
}
.mc-mono { font-family: 'SFMono-Regular', Consolas, monospace; font-size: .82rem; color: #6B6480; }

/* Streamlit widget softening — buttons become storybook stones */
div.stButton > button {
  font-family: 'EB Garamond', Georgia, serif; font-size: 1.02rem;
  border-radius: 14px; padding: .62rem 1.05rem; width: 100%; text-align: left;
  background: linear-gradient(180deg, rgba(255,255,255,.95), rgba(241,235,247,.88));
  color: #33304A; border: 1px solid rgba(124,107,168,.34);
  box-shadow: 0 3px 10px rgba(63,91,68,.09);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
div.stButton > button:hover {
  transform: translateY(-2px);
  border-color: #C9A227;
  box-shadow: 0 10px 22px rgba(124,107,168,.22);
}
div.stButton > button:active { transform: translateY(0); }

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(241,235,247,.92), rgba(238,244,236,.92));
  border-right: 1px solid rgba(124,107,168,.18);
}
[data-testid="stSidebar"] * { color: #33304A; }

h1, h2, h3 { font-family: 'Cinzel', serif !important; color: #3F5B44 !important; letter-spacing: .02em; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, tagline: str) -> None:
    st.markdown(
        f'<div class="mc-hero"><h1 class="mc-title">{title}</h1>'
        f'<div class="mc-tagline">{tagline}</div><div class="mc-rule"></div></div>',
        unsafe_allow_html=True,
    )


def pill(text: str, variant: str = "") -> str:
    return f'<span class="mc-pill {variant}">{text}</span>'


def meter(label: str, value: int, maximum: int = 100, suffix: str = "") -> None:
    pct = max(0, min(100, int(value / maximum * 100) if maximum else 0))
    shown = f"{value}{suffix}"
    st.markdown(
        f'<div class="mc-mono">{label} · {shown}</div><div class="mc-meter"><span style="width:{pct}%"></span></div>',
        unsafe_allow_html=True,
    )
