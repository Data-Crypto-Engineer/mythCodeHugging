"""Graceful failure: classification, bounded retries, scrubbing, safe fallbacks.

Design rules honoured here:
  * Authentication / configuration errors are NEVER retried.
  * Rate limits and connection errors are retried a bounded number of times.
  * Nothing secret is ever logged.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar

from utils.logger import get_logger

logger = get_logger("errors")
T = TypeVar("T")

# ── Secret scrubbing ──────────────────────────────────────────────
# Matches Google AI keys (AIza...), Groq keys (gsk_...), bearer tokens and long hex blobs.
_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z\-_]{10,}"),
    re.compile(r"gsk_[0-9A-Za-z]{10,}"),
    re.compile(r"(?i)bearer\s+[0-9A-Za-z\-_.]{12,}"),
    re.compile(r"\b[0-9a-f]{32,}\b"),
)


def scrub(text: Any) -> str:
    """Remove anything that looks like a credential from a log/message."""
    out = str(text)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[redacted]", out)
    return out


# ── Error taxonomy ────────────────────────────────────────────────
class MythCodeError(Exception):
    """Base class. `user_message` is safe to show a player."""

    user_message = "Something in the weave slipped. The story has been held safely."


class ConfigurationError(MythCodeError):
    user_message = "MythCode is not fully configured. Check the Settings screen."


class AuthError(MythCodeError):
    """Permanent: bad/missing key. Never retried."""
    user_message = "The story-brain key was refused. Please check your API credentials."


class QuotaError(MythCodeError):
    user_message = "The story-brain has run out of allowance for now. Try again later."


class RateLimitError(MythCodeError):
    """Transient: retried."""
    user_message = "The story-brain is busy. Retrying shortly..."


class ProviderUnavailable(MythCodeError):
    """Transient: timeout / connection / 5xx. Retried."""
    user_message = "The story-brain could not be reached. Retrying shortly..."


class MalformedOutputError(MythCodeError):
    """The model answered, but not with usable structure. Retried once."""
    user_message = "The story arrived tangled; smoothing it back into shape."


class StateValidationError(MythCodeError):
    user_message = "That change would have broken the world. Nothing was saved."


_TRANSIENT_HINTS = ("rate limit", "429", "timeout", "timed out", "connection", "temporarily", "503", "502", "500", "overloaded")
_PERMANENT_HINTS = ("api key", "unauthorized", "401", "403", "authentication", "permission", "invalid key", "not found")


def classify(exc: BaseException) -> MythCodeError:
    """Map any provider/application exception onto our taxonomy."""
    if isinstance(exc, MythCodeError):
        return exc
    name = type(exc).__name__.lower()
    text = f"{name} {exc}".lower()

    if any(h in text for h in _PERMANENT_HINTS):
        return AuthError(scrub(exc))
    if "ratelimit" in name or "429" in text:
        return RateLimitError(scrub(exc))
    if "quota" in text or "insufficient_quota" in text:
        return QuotaError(scrub(exc))
    if any(h in text for h in _TRANSIENT_HINTS) or "connection" in name or "timeout" in name:
        return ProviderUnavailable(scrub(exc))
    if isinstance(exc, (KeyError, FileNotFoundError)):
        return ConfigurationError(scrub(exc))
    return MythCodeError(scrub(exc))


def log_exception(exc: BaseException, where: str, level: str = "warning") -> MythCodeError:
    """Classify, log safely, return the classified error."""
    err = classify(exc)
    getattr(logger, level, logger.warning)("[%s] %s: %s", where, type(err).__name__, scrub(exc))
    return err


@dataclass
class RescueResult:
    value: Any = None
    error: MythCodeError | None = None
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and self.value is not None


def run_with_rescue(
    func: Callable[..., T],
    *args: Any,
    retries: int = 2,
    backoff: float = 0.8,
    where: str = "unknown",
    retry_on: Iterable[type[BaseException]] = (RateLimitError, ProviderUnavailable, MalformedOutputError),
    **kwargs: Any,
) -> RescueResult:
    """Call func with bounded retries. Never raises; returns a RescueResult.

    AuthError / ConfigurationError / QuotaError abort immediately: retrying a
    bad credential or an exhausted quota only wastes the player's time.
    """
    attempt = 0
    last: MythCodeError | None = None
    while attempt <= retries:
        attempt += 1
        try:
            return RescueResult(value=func(*args, **kwargs), attempts=attempt)
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all boundary
            err = log_exception(exc, where)
            last = err
            if not isinstance(err, tuple(retry_on)) or attempt > retries:
                break
            time.sleep(backoff * attempt)
    logger.warning("[%s] giving up after %d attempt(s)", where, attempt)
    return RescueResult(error=last, attempts=attempt)


def user_message(err: MythCodeError | None, default: str | None = None) -> str:
    if err is None:
        return default or "Something unexpected happened, and the story was held safely."
    return err.user_message
