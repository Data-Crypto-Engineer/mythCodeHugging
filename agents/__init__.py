"""CrewAI agents + the Flow orchestrator.

Import order note: agent modules import from `core` and `models` only; `core`
imports `agents.mythcode_crew` lazily INSIDE functions to avoid a circular import.
"""
