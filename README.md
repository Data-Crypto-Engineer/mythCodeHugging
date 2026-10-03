# ✦ MythCode

**An adaptive fantasy world where every choice teaches you something.**

> *Your choices shape the world. Your world shapes your mind.*

MythCode is a multi-agent AI fantasy adventure that teaches real Python by disguising
computational thinking as world mechanics. You arrive in Whispering Village where the
waterwheel has fallen silent, and you repair the world by discovering the rules inside it —
a guardian that obeys ordered commands, a door that decides, a river of repeating tiles.
Only after you have *felt* an idea does the game reveal its name and its Python.

---

## Table of contents

- [What it is](#what-it-is)
- [Verified stack](#verified-stack)
- [Architecture](#architecture)
- [The six agents](#the-six-agents)
- [Learning design](#learning-design)
- [Installation](#installation)
- [Local execution](#local-execution)
- [Secrets configuration](#secrets-configuration)
- [Testing](#testing)
- [Deployment to Streamlit Community Cloud](#deployment-to-streamlit-community-cloud)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## What it is

A working prototype — not a mockup. You can create a character, receive generated scenes,
make choices that permanently change world values, solve three deterministic programming
challenges, build magical inventions from blocks, and read a Learning Journal that records
only what you actually solved.

**Two modes, honestly labelled in the UI:**

| Mode | When | What changes |
|---|---|---|
| **Live** | `GEMINI_API_KEY` **and** `GROQ_API_KEY` present | Full agent crew: Gemini directs, Groq weaves story, analyses you, guards continuity, frames and hints challenges |
| **Storyteller's Simulator** | No keys | Deterministic director, templated scenes, static hints. **Every** puzzle, rule check, memory, validator and save still works |

Offline mode exists so the app is demoable, testable and cheap — and so unit tests never
touch a paid API.

## Verified stack

Verified against live documentation in **October 2026**:

| Component | Version / fact | Source |
|---|---|---|
| Python | **3.12** (CrewAI allows `>=3.10,<3.14`; 3.13 wheels are still flaky on Cloud) | [PyPI crewai](https://pypi.org/project/crewai/) |
| CrewAI | `>=1.15,<2` — Flows via `crewai.flow.flow`, Pydantic state, `@router` string labels | [Flows docs](https://docs.crewai.com/edge/en/concepts/flows) |
| LiteLLM | **required explicitly** — CrewAI has no native `groq/` provider | [llm.py](https://github.com/crewAIInc/crewAI/blob/f7ba8e35/lib/crewai/src/crewai/llm.py) |
| Gemini | `google-genai` `<3.0.0`, native CrewAI provider `gemini/...` | [python-genai](https://github.com/googleapis/python-genai) |
| Groq | `groq` SDK; production IDs `openai/gpt-oss-120b`, `llama-3.1-8b-instant` | [Groq models](https://console.groq.com/docs/models.md) |
| Streamlit | `>=1.40,<2`; `st.secrets` dict + attribute; **working dir = repo root** | [st.secrets](https://docs.streamlit.io/develop/api-reference/connections/st.secrets) |
| Imagery | Cloudflare Workers AI `@cf/black-forest-labs/flux-1-schnell` | [Workers AI](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/) |
| Persistent store | SQLite (see [limitations](#known-limitations)) | — |

> **`runtime.txt` is inert on Streamlit Community Cloud.** The platform ignores it and uses
> the interpreter selected in **Advanced settings**. Target 3.12 there too.

## Architecture

```
Player action (Streamlit button)
        │
        ▼
app.py ──► core/game_engine.py ──► agents/mythcode_crew.py   ◄── CrewAI Flow
                                        │
        ┌───────────────────────────────┴─────────────────────────────┐
        │  @start open_turn                                           │
        │  @router route_action ──► "challenge" | "normal"            │
        │  @listen normal   Director (Gemini)                         │
        │  @listen challenge Learning frame + Director                │
        │  @listen adapt_player  Player Insight (Groq, bounded)       │
        │  @listen tell_story    Story Weaver (Groq)                  │
        │  @listen keep_world    World Keeper (Groq) ──► validate     │
        │  @listen guard ─► @router decide ─► "approved" | "blocked"  │
        │  @listen blocked   predefined safe scene (state preserved)  │
        │  @listen commit    apply validated changes + learning write │
        └─────────────────────────────────────────────────────────────┘
        │
        ▼
core/state_validator.py  (deterministic gate)  ──►  database/storage.py (SQLite)
```

**Business logic never lives in `app.py`.** The UI renders and dispatches; the engine decides.

## The six agents

| # | Agent | Brain | Responsibility | Cannot |
|---|---|---|---|---|
| 1 | **Director** | **Gemini** | Reads world + player + quest, chooses the next beat, proposes state changes | Mutate state, overwrite the world, skip concepts |
| 2 | **Player Insight** | Groq | Emits bounded preference **deltas** from observed behaviour | Label you, infer intelligence/identity/wellbeing |
| 3 | **Story Weaver** | Groq | Writes scene, dialogue, choices, consequence teasers | Claim you learned something; omit a due challenge |
| 4 | **World Keeper** | Groq | Continuity, world patches, character memories | Save anything — values are filtered first |
| 5 | **Logic & Learning** | Groq | Frames challenges, hints, Python reveals | Decide correctness; generate the Python example |
| 6 | **Continuity & Safety** | Groq | Continuity, world rules, age-appropriateness, unsupported claims | Be the only check — Python validators always run |

## Learning design

Three mechanics ship in the prototype, plus a fourth that crosses into reading real Python:

| Concept | World mechanic | Python revealed |
|---|---|---|
| **Sequence** | Guide a clockwork guardian tile by tile | `move_forward()` … one line at a time |
| **Conditions** | Write one rule for a door that must hold in *every* situation | `if has_key:` / `else:` |
| **Loops** | Cross repeating river tiles with as few blocks as possible | `for step in range(5):` |
| **Code assembly** | Rebuild the first scroll by ordering real Python lines | `tiles = 5` + `range(tiles)` |

**Correctness is never an LLM opinion.** `core/learning_engine.py` simulates the guardian,
tests the rule against every scenario, and expands loops — so a beautiful hallucination
cannot pass an invalid solution, and a correct one cannot be failed. `eval()` and `exec()`
appear nowhere in the codebase (enforced by a test).

## Installation

```bash
git clone https://github.com/<your-username>/mythcode.git
cd mythcode

python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt
```

## Local execution

```bash
# ALWAYS from the repository root — Streamlit Cloud runs from there too,
# and some Streamlit paths resolve against the working directory.
streamlit run app.py
```

The game runs immediately with **no keys at all** (offline mode). Add keys for full prose.

## Secrets configuration

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

```toml
GEMINI_API_KEY = "..."          # Director — aistudio.google.com
GROQ_API_KEY   = "..."          # all other agents — console.groq.com

[cloudflare]                     # optional; imagery only
ACCOUNT_ID = "..."
API_TOKEN  = "..."

[models]
GEMINI_MODEL    = "gemini/gemini-flash-latest"
GROQ_MODEL      = "groq/openai/gpt-oss-120b"
GROQ_MODEL_FAST = "groq/llama-3.1-8b-instant"

[app]
MODE = "auto"                    # auto | live | offline
```

`.streamlit/secrets.toml` is git-ignored. **Never commit it.**

## Testing

```bash
pytest -q
```

Every test runs **offline** — `tests/conftest.py` forces `MODE=offline` and strips API keys,
so **no unit test ever makes a paid API call**. Coverage:

`test_state_validation.py` · valid/invalid transitions, monotonic history, enum guards
`test_learning_engine.py` · sequence/condition/loop/assembly verdicts, staged unlocking, no `eval`
`test_player_model.py` · bounded, reversible, non-sensitive adaptation
`test_game_engine.py` · new game, character creation, turns, persistence, corrupted saves
`test_error_handling.py` · missing keys, secret scrubbing, retry policy, malformed output, state preservation

## Deployment to Streamlit Community Cloud

1. Push the repo to GitHub (public or private).
2. Go to <https://share.streamlit.io> → **Create app** → **Deploy a public app from GitHub**.
3. Repository: `your-username/mythcode` · Branch: `main` · **Main file path: `app.py`**.
4. Open **Advanced settings → Python version** and choose **3.12**
   (*`runtime.txt` is ignored here — this dropdown is the only control that matters*).
5. Paste your secrets into **Advanced settings → Secrets** (same TOML as above).
6. **Deploy.** Watch the build log; the first build installs CrewAI and takes a few minutes.

> I have **not** deployed this — I can't. Everything above is written to be deployable, but
> treat the first build as unverified until you see it succeed.

## Known limitations

Honest list, no hedging:

1. **SQLite on Community Cloud is not durable.** The container filesystem is ephemeral: saves
   survive reruns and session restarts but **not** a redeploy or container recycle. The app
   detects a read-only filesystem and falls back to in-memory storage, warning you in Settings.
   Durable cloud saves need an external store — deliberately **not** added (external service).
2. **`LLM.call()`'s exact signature is not fully pinned** in the docs I verified. `agents/llm_factory.py`
   tries the documented string form, falls back to the messages form, and returns `None` rather than
   raising — so a signature change degrades to offline prose instead of crashing a turn.
3. **Model IDs rotate.** Every model is a configurable secret; defaults are aliases/current IDs.
4. **Deployment is unverified.** I verified APIs, not your hosted build.
5. **Imagery depends on a Cloudflare account.** Without it, scenes render text-only.
6. **Learning is deterministic by design.** AI frames and explains; it never grades. This caps
   narrative cleverness in the puzzle layer — intentional, and unit-tested.
7. **Two defects I did not silently patch** in the code artifacts: a stray `game = state_validator`
   line in `commit()`, and a `validate_and_report` helper you must append to `core/state_manager.py`
   (snippet provided in the artifact). Fix these before running.
8. **No collaborative world-building or teacher dashboard yet** — see the roadmap.

## Roadmap

- **v0.2** Free-text Python challenges with a sandboxed AST-allowlist checker (**never** `eval`)
- **v0.3** Visual programming blocks wired to the same deterministic validator
- **v0.4** Procedurally generated locations from a seeded grammar
- **v0.5** Durable saves via libSQL/Turso (opt-in, free tier) — **your call, not assumed**
- **v0.6** More kingdoms (Elarion is one of five planned), deeper NPC memory summarisation
- **v0.7** Optional teacher/parent dashboard reading `LearningProgress` only
- **v0.8** Collaborative world-building across sessions

## License

MIT. Built for learners, not for surveillance — no sensitive trait is ever inferred or stored.

---

*MythCode — an AI fantasy world that learns how you play, evolves with your choices, and teaches you to create the rules of your own universe.*
