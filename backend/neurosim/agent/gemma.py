"""Gemma 4 through the Gemini API (CS2), used when config.LLM is "gemma".

The Gemini API serves Gemma on the free tier with the same GEMINI_API_KEY,
but only through generate_content: there is no server-side conversation
(agent.py keeps the history) and no PDF input (papers.py sends text anyway).
Function calling, system instructions and JSON output work as for Gemini.
Every call still goes through gemini.call, so the rate-limit and overload
guards are the same for both families.
"""

from __future__ import annotations

import json

from google.genai import types

from neurosim import config
from neurosim.agent import gemini
from neurosim.agent.tools import TOOL_DECLARATIONS


def _thinking(level: str) -> types.ThinkingConfig:
    # Gemma only thinks or doesn't. Our "low" means off, anything above means on.
    return types.ThinkingConfig(thinking_level="MINIMAL" if level in ("minimal", "low") else "HIGH")


def generation_config(system: str, *, thinking_level: str, max_output_tokens: int, timeout: float, **extra) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system,
        thinking_config=_thinking(thinking_level),
        max_output_tokens=max_output_tokens,
        # A per-request http_options replaces the client's, so repeat the
        # no-retry setting (see gemini.HTTP_OPTIONS). The SDK wants milliseconds.
        http_options=gemini.HTTP_OPTIONS.model_copy(update={"timeout": int(timeout * 1000)}),
        **extra,
    )


def generate(model: str, contents, cfg: types.GenerateContentConfig) -> types.GenerateContentResponse:
    return gemini.client().models.generate_content(model=model, contents=contents, config=cfg)


def content(response) -> types.Content:
    """The model's turn, to append to the history as is (it carries the
    thought signatures the next call needs)."""
    candidates = response.candidates or []
    if not candidates or candidates[0].content is None:
        reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        raise gemini.GeminiUnavailable(f"Gemma returned no answer ({reason or 'empty response'}). Try again.")
    return candidates[0].content


def text(response) -> str:
    """The answer without the thinking."""
    return "".join(p.text for p in content(response).parts or [] if p.text and not p.thought).strip()


def function_tools() -> list[types.Tool]:
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=d["name"],
            description=d["description"],
            parameters_json_schema=d["parameters"] if d["parameters"]["properties"] else None,
        )
        for d in TOOL_DECLARATIONS
    ])]


def json_text(model: str, *, system: str, schema: dict, text_input: str, thinking_level: str,
              max_output_tokens: int, timeout: float) -> str:
    """Ask for one JSON object matching schema and return the raw text."""
    cfg = generation_config(
        system + "\nAnswer with one JSON object and nothing else. It must follow this JSON schema:\n"
        + json.dumps(schema),
        thinking_level=thinking_level,
        max_output_tokens=max_output_tokens,
        timeout=timeout,
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    return text(generate(model, text_input, cfg))
