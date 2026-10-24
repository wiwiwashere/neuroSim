"""One place that talks to Gemini (CS2): the client, and the free-tier guards
every call shares (agent turns, run summaries, paper extraction).

On a 429 (rate limit) we wait the delay the API suggests, retry once, then
switch to config.AGENT_FALLBACK_MODEL. An overloaded model (503, 500 or a
timeout) switches to the fallback straight away, and later calls stay on the
fallback for config.AGENT_FALLBACK_COOLDOWN_S so each turn doesn't wait for
Flash to time out again. Any other API error becomes a
GeminiUnavailable with a message a person can act on, which the API turns
into a 503.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from google import genai

from neurosim import config

_client: genai.Client | None = None
_fallback_until = 0.0   # time.monotonic() until which calls skip AGENT_MODEL


class GeminiUnavailable(RuntimeError):
    """Gemini refused or failed the call; the message says why in plain words."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def client() -> genai.Client:
    # Created on first use so importing never needs credentials.
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def _status(err: Exception) -> int | None:
    # Interactions errors carry status_code; generate_content errors carry code.
    for attr in ("status_code", "code"):
        value = getattr(err, attr, None)
        if isinstance(value, int):
            return value
    return None


def _retry_delay(err: Exception) -> float:
    response = getattr(err, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    if header and header.replace(".", "", 1).isdigit():
        return float(header)
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(getattr(err, "body", "")) + str(err))
    return float(m.group(1)) if m else 5.0


def _plain(err: Exception, status: int | None) -> str:
    text = str(err)
    if status == 402 or "prepayment credits" in text:
        return ("Gemini refused the key: its AI Studio project has billing on and no credit left. "
                "Use a key from a project without billing to stay on the free tier.")
    if status in (401, 403) or "API key" in text:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in .env."
    if status == 429:
        return "Gemini's free-tier rate limit is used up on both models. Try again in a minute."
    if status in (500, 503) or status is None:
        return "Gemini is overloaded or not responding on both models right now. Try again in a minute."
    return f"Gemini call failed ({status or 'no status'}): {text[:300]}"


def call(fn: Callable[[str], Any], state: dict | None = None) -> Any:
    """Run fn(model) with the free-tier guards. state["model"] remembers a
    switch to the fallback, so the rest of a turn stays on it. fn should pass
    timeout=config.AGENT_REQUEST_TIMEOUT_S to the SDK."""
    global _fallback_until
    state = state if state is not None else {}
    default = config.AGENT_FALLBACK_MODEL if time.monotonic() < _fallback_until else config.AGENT_MODEL
    model = state.setdefault("model", default)
    retried = False
    while True:
        try:
            return fn(model)
        except Exception as err:  # the SDK raises a different class per API surface
            status = _status(err)
            if status is None and not hasattr(err, "body"):
                raise  # not an API error: a bug on our side
            if status == 429 and not retried:
                retried = True
                time.sleep(min(_retry_delay(err), config.AGENT_RETRY_MAX_WAIT_S))
                continue
            overloaded = status in (500, 503) or (status is None and "timed out" in str(err).lower())
            if (status == 429 or overloaded) and model != config.AGENT_FALLBACK_MODEL:
                model = state["model"] = config.AGENT_FALLBACK_MODEL
                _fallback_until = time.monotonic() + config.AGENT_FALLBACK_COOLDOWN_S
                continue
            raise GeminiUnavailable(_plain(err, status), status) from err
