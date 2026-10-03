"""Deterministic validators shared by agents, core and tests.

Objective truth lives here — never delegated to an LLM.
"""
from __future__ import annotations

import json
import re
from typing import Any

# A deliberately small, conservative pre-filter. The Continuity agent adds LLM
# review on top; this exists so that even OFFLINE mode cannot emit banned content.
_BANNED = re.compile(
    r"\b(kill yourself|suicide|self[- ]?harm|behead|dismember|gore|torture|"
    r"rape|sexual|explicit sex|nazi|slur)\b",
    re.IGNORECASE,
)
MAX_TEXT_LEN = 2600


def scrub_text(value: Any, limit: int = MAX_TEXT_LEN) -> str:
    """Collapse whitespace and cap length so no single field can blow the context."""
    if value is None:
        return ""
    text = re.sub(r"[ \t]+", " ", str(value)).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit]


def clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))


def clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    return int(round(clamp(value, low, high, default)))


def is_child_safe(text: str) -> bool:
    return not _BANNED.search(text or "")


def is_plausible_text(text: Any, min_len: int = 1) -> bool:
    return isinstance(text, str) and len(text.strip()) >= min_len


def extract_json_block(text: Any) -> dict[str, Any] | None:
    """Best-effort JSON extraction: strips fences, then brace-matches.

    LLMs wrap JSON in prose or markdown fences surprisingly often; failing the
    whole turn over a stray ```json is unacceptable in a player-facing game.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z0-9_]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            ch = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start : index + 1])
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        break
        start = cleaned.find("{", start + 1)
    return None


def slugify(text: str, fallback: str = "action") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return slug[:40] or fallback
