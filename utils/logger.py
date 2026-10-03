"""Central logging. Never logs secret values (see utils.error_handler.scrub)."""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-26s | %(message)s"


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    root = logging.getLogger("mythcode")
    root.setLevel(logging.INFO)
    root.propagate = False
    if not root.handlers:
        root.addHandler(handler)
    # CrewAI/LiteLLM are extremely chatty at INFO.
    for noisy in ("crewai", "litellm", "LiteLLM", "httpx", "groq", "google_genai", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger, e.g. get_logger('director')."""
    _configure_root()
    return logging.getLogger(f"mythcode.{name}" if not name.startswith("mythcode") else name)
