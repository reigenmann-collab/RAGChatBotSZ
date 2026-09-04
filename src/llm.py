"""Thin Gemini client wrapper. Structured output is obtained through Gemini's
native JSON response schema, so the pipeline never has to parse free-form JSON
out of prose."""
from __future__ import annotations

import sys
import time
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import api_key, model_name  # noqa: E402

# The google-genai SDK already retries transient failures internally (via
# tenacity), but under real load - a busy free-tier endpoint, a live demo with
# several people hitting it at once - it can still exhaust its own retries and
# raise ServerError (5xx). One extra retry pass here, on top of the SDK's own,
# meaningfully improves demo reliability without masking a genuinely broken key
# or a persistent outage (ClientError, e.g. 4xx auth/quota problems, is not
# retried - retrying a bad key just wastes time).
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0


def _call_with_retry(fn):
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fn()
        except genai_errors.ServerError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise last_exc  # noqa: RSE102 - re-raising the last transient failure


@lru_cache(maxsize=1)
def client() -> genai.Client:
    return genai.Client(api_key=api_key())


def structured(
    *,
    system: str,
    user: str,
    tool_name: str,
    schema: dict,
    max_tokens: int = 1200,
    temperature: float = 0.0,
    model: str | None = None,
) -> dict:
    """Call the model and return its JSON response parsed as a dict.

    `tool_name` is unused by Gemini's native JSON mode; kept so callers written
    against the earlier tool-use interface did not need to change.

    gemini-3.6-flash is a reasoning model: it spends a variable, non-zero number
    of tokens "thinking" before writing any output, and that budget cannot be
    forced to zero on this model. If max_tokens is too tight the response is
    truncated mid-thought with no JSON at all - raised here as a clear,
    actionable error rather than a confusing JSONDecodeError two frames away.
    """
    import json

    resp = _call_with_retry(
        lambda: client().models.generate_content(
            model=model or model_name(),
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
    )
    finish_reason = resp.candidates[0].finish_reason if resp.candidates else None
    if not resp.text:
        raise RuntimeError(
            f"model returned no content for {tool_name} "
            f"(finish_reason={finish_reason}). "
            "If this is MAX_TOKENS, raise max_tokens - the model's internal "
            "thinking consumes part of the budget before any output is written."
        )
    try:
        return json.loads(resp.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"model response for {tool_name} was not valid JSON "
            f"(finish_reason={finish_reason}): {resp.text[:300]!r}"
        ) from exc


def vision_transcribe(
    *,
    system: str,
    image_bytes: bytes,
    mime_type: str = "image/png",
    max_tokens: int = 4000,
    model: str | None = None,
) -> str:
    """Send one image and return the model's plain-text reply (used for OCR)."""
    resp = _call_with_retry(
        lambda: client().models.generate_content(
            model=model or model_name(),
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.0,
                max_output_tokens=max_tokens,
            ),
        )
    )
    return (resp.text or "").strip()
