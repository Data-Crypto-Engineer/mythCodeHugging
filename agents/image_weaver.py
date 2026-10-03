"""Cloudflare Workers AI imagery (optional).

VERIFIED: POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}
  header: Authorization: Bearer {API_TOKEN}
  body:   {"prompt": "...", "steps": 4}
  result: {"result": {"image": "<base64 JPEG>"}, "success": true}

The model is configurable because Cloudflare's catalogue moves fast; the default
`@cf/black-forest-labs/flux-1-schnell` uses simple JSON. If the configured model is
one of the multipart FLUX.2 variants (flux-2-dev / flux-2-klein-*), we switch to
multipart form-data automatically. When anything fails we return None and the UI
falls back to a bundled SVG banner — imagery must never break the game.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any

from utils.config import get_settings
from utils.error_handler import log_exception
from utils.logger import get_logger
from utils.validators import scrub_text

logger = get_logger("imagery")

MULTIPART_MODELS = ("flux-2-dev", "flux-2-klein-4b", "flux-2-klein-9b")
STYLE_SUFFIX = (
    "storybook illustration, soft watercolour and gouache, misty lavender, soft sage, "
    "warm cream, muted gold, gentle golden light, wide establishing shot, painterly, "
    "wholesome children's fantasy, no text, no words, no watermark"
)


def _endpoint(account_id: str, model: str) -> str:
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"


def is_multipart(model: str) -> bool:
    return any(tag in model for tag in MULTIPART_MODELS)


def build_prompt(scene_title: str, description: str, location: str) -> str:
    core = f"{scene_title}. {description[:220]}. Setting: {location}."
    return scrub_text(f"{core} {STYLE_SUFFIX}", 2040)


def generate_scene_image(
    scene_title: str, description: str, location: str, seed: int | None = None
) -> str | None:
    """Return a data URI (data:image/jpeg;base64,...) or None if unavailable."""
    settings = get_settings()
    if not settings.has_cloudflare:
        return None

    prompt = build_prompt(scene_title, description, location)
    if seed is None:
        digest = hashlib.sha256(f"{scene_title}|{location}".encode("utf-8")).hexdigest()
        seed = int(digest[:6], 16)

    try:
        import httpx

        url = _endpoint(settings.cf_account_id or "", settings.cf_image_model)
        headers = {"Authorization": f"Bearer {settings.cf_api_token}"}

        with httpx.Client(timeout=60.0) as client:
            if is_multipart(settings.cf_image_model):
                response = client.post(
                    url, headers=headers,
                    data={"prompt": prompt, "width": "1024", "height": "768", "seed": str(seed)},
                )
            else:
                response = client.post(
                    url, headers={**headers, "Content-Type": "application/json"},
                    json={"prompt": prompt, "steps": 4, "seed": seed},
                )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        result = payload.get("result") or {}
        image_b64 = result.get("image") or payload.get("image")
        if not image_b64:
            logger.warning("Cloudflare returned no image field: %s", list(payload)[:6])
            return None
        if isinstance(image_b64, str) and image_b64.startswith("data:"):
            return image_b64
        return f"data:image/jpeg;base64,{image_b64}"
    except Exception as exc:  # imagery is decorative; failure is never fatal
        log_exception(exc, "imagery.generate_scene_image")
        return None
