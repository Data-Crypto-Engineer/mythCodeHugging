"""One place where every model is configured.

VERIFIED (CrewAI docs, Oct 2026):
  * LLM(model="gemini/<id>", api_key=...) uses CrewAI's NATIVE Gemini provider.
  * LLM(model="groq/<id>") has no native provider -> it falls back to LiteLLM,
    which is why `litellm` is a pinned dependency in requirements.txt.

UNVERIFIED AND THEREFORE DEFENDED: the exact parameter acceptance of LLM.call()
across providers. `call_json` below tries the documented string form first and
then the messages form, and always degrades to `None` instead of raising.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from utils.config import Settings, get_settings
from utils.error_handler import MalformedOutputError, run_with_rescue, scrub
from utils.logger import get_logger
from utils.validators import extract_json_block

logger = get_logger("llm")
M = TypeVar("M", bound=BaseModel)


@lru_cache(maxsize=8)
def _build_llm(model: str, api_key: str, temperature: float) -> Any:
    from crewai import LLM

    return LLM(model=model, api_key=api_key, temperature=temperature)


def director_llm(settings: Settings | None = None) -> Any:
    """The Director's brain — Gemini, per the architecture spec."""
    settings = settings or get_settings()
    return _build_llm(settings.gemini_model, settings.gemini_api_key or "", 0.75)


def weaver_llm(settings: Settings | None = None) -> Any:
    """Narrative brain — Groq, tuned for expressive prose."""
    settings = settings or get_settings()
    return _build_llm(settings.groq_model, settings.groq_api_key or "", 0.85)


def reasoner_llm(settings: Settings | None = None) -> Any:
    """Analysis brain used by Insight / Learning / Safety — lower temperature."""
    settings = settings or get_settings()
    return _build_llm(settings.groq_model, settings.groq_api_key or "", 0.3)


def fast_llm(settings: Settings | None = None) -> Any:
    settings = settings or get_settings()
    return _build_llm(settings.groq_model_fast, settings.groq_api_key or "", 0.4)


def _invoke(llm: Any, prompt: str) -> str:
    """Call the CrewAI LLM, tolerating both the string and messages signatures."""
    try:
        raw = llm.call(prompt)
    except TypeError:
        raw = llm.call(messages=[{"role": "user", "content": prompt}])
    except Exception:
        raise
    if raw is None:
        raise MalformedOutputError("empty model response")
    text = raw if isinstance(raw, str) else str(raw)
    if not text.strip():
        raise MalformedOutputError("empty model response")
    return text


def call_json(llm: Any, prompt: str, schema: type[M], *, retries: int = 2, where: str = "llm") -> M | None:
    """Ask for structured output and return a validated model, or None.

    Never raises. The caller decides the fallback (an agent's offline path or a
    predefined safe scene), which keeps a malformed answer from ending a turn.
    """
    keys = list(schema.model_json_schema().get("properties", {}).keys())
    guided = (
        f"{prompt}\n\n"
        f"Reply with ONE JSON object and nothing else. "
        f"Required keys: {', '.join(keys)}. No markdown fences, no commentary."
    )

    def _attempt() -> M:
        text = _invoke(llm, guided)
        data = extract_json_block(text)
        if data is None:
            raise MalformedOutputError(f"no JSON object found in: {scrub(text)[:160]}")
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            missing = ", ".join(str(err['loc'][0]) for err in exc.errors() if err.get("loc"))
            raise MalformedOutputError(f"schema mismatch (check: {missing or 'types'})") from exc

    result = run_with_rescue(_attempt, retries=retries, where=where)
    if result.ok:
        return result.value
    logger.warning("[%s] structured call failed after %d attempt(s)", where, result.attempts)
    return None
