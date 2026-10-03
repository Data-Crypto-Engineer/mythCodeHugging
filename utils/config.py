"""Configuration + secrets access.

Verified behaviour (Streamlit docs):
  * st.secrets supports BOTH dict and attribute access.
  * A missing key raises KeyError; a missing secrets.toml raises FileNotFoundError.
  * No API key is ever hardcoded here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from utils.logger import get_logger

logger = get_logger("config")

DEFAULT_GEMINI_MODEL = "gemini/gemini-flash-latest"
DEFAULT_GROQ_MODEL = "groq/openai/gpt-oss-120b"
DEFAULT_GROQ_FAST_MODEL = "groq/llama-3.1-8b-instant"
DEFAULT_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"


def read_secret(*path: str, default: str | None = None) -> str | None:
    """Read a nested secret from st.secrets, then fall back to environment vars.

    read_secret("cloudflare", "API_TOKEN") reads secrets["cloudflare"]["API_TOKEN"]
    then falls back to os.environ["CLOUDFLARE_API_TOKEN"].
    """
    try:
        import streamlit as st  # imported lazily: works outside Streamlit too

        node: Any = st.secrets
        found = True
        for part in path:
            try:
                if part in node:
                    node = node[part]
                else:
                    found = False
                    break
            except Exception:
                found = False
                break
        if found and isinstance(node, (str, int, float)) and str(node).strip():
            return str(node).strip()
    except Exception:
        # FileNotFoundError (no secrets.toml) or Streamlit not running.
        pass

    env_keys = ["_".join(path).upper(), path[-1].upper()]
    for key in env_keys:
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    return default


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    groq_api_key: str | None
    gemini_model: str
    groq_model: str
    groq_model_fast: str
    cf_account_id: str | None
    cf_api_token: str | None
    cf_image_model: str
    db_path: str
    story_seed: str
    requested_mode: str

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_cloudflare(self) -> bool:
        return bool(self.cf_account_id and self.cf_api_token)

    @property
    def mode(self) -> str:
        """'live' when the requested brains are available, else 'offline'."""
        if self.requested_mode == "offline":
            return "offline"
        if self.requested_mode == "live":
            return "live" if (self.has_gemini and self.has_groq) else "offline"
        return "live" if (self.has_gemini and self.has_groq) else "offline"

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def diagnostics(self) -> dict[str, Any]:
        """Safe, secret-free summary for the Settings screen."""
        return {
            "mode": self.mode,
            "gemini_key": "configured" if self.has_gemini else "missing",
            "groq_key": "configured" if self.has_groq else "missing",
            "cloudflare": "configured" if self.has_cloudflare else "missing",
            "gemini_model": self.gemini_model,
            "groq_model": self.groq_model,
            "groq_model_fast": self.groq_model_fast,
            "image_model": self.cf_image_model,
            "db_path": self.db_path,
            "story_seed": self.story_seed,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings. Call get_settings.cache_clear() if secrets change."""
    requested = (read_secret("app", "MODE", default="auto") or "auto").lower()
    if requested not in {"auto", "live", "offline"}:
        requested = "auto"
    return Settings(
        gemini_api_key=read_secret("GEMINI_API_KEY"),
        groq_api_key=read_secret("GROQ_API_KEY"),
        gemini_model=read_secret("models", "GEMINI_MODEL", default=DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL,
        groq_model=read_secret("models", "GROQ_MODEL", default=DEFAULT_GROQ_MODEL) or DEFAULT_GROQ_MODEL,
        groq_model_fast=read_secret("models", "GROQ_MODEL_FAST", default=DEFAULT_GROQ_FAST_MODEL) or DEFAULT_GROQ_FAST_MODEL,
        cf_account_id=read_secret("cloudflare", "ACCOUNT_ID"),
        cf_api_token=read_secret("cloudflare", "API_TOKEN"),
        cf_image_model=read_secret("cloudflare", "IMAGE_MODEL", default=DEFAULT_IMAGE_MODEL) or DEFAULT_IMAGE_MODEL,
        db_path=read_secret("app", "DB_PATH", default="mythcode.db") or "mythcode.db",
        story_seed=read_secret("app", "STORY_SEED", default="eldertree") or "eldertree",
        requested_mode=requested,
    )
