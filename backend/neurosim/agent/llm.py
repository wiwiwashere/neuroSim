"""The one-shot JSON call behind the run summary and paper extraction (CS2),
for either model family (config.LLM). The agent's chat loop branches in
agent.py instead, because the two families keep a conversation differently.
"""

from __future__ import annotations

import json
import re

from neurosim import config
from neurosim.agent import gemini, gemma


def json_reply(model: str, *, system: str, schema: dict, prompt: str, thinking_level: str,
               max_output_tokens: int, timeout: float) -> str:
    """Raw JSON text from one call; pass it to gemini.call as fn(model)."""
    if config.LLM == "gemma":
        return gemma.json_text(model, system=system, schema=schema, text_input=prompt, thinking_level=thinking_level,
                               max_output_tokens=max_output_tokens, timeout=timeout)
    interaction = gemini.client().interactions.create(
        model=model,
        input=prompt,
        system_instruction=system,
        response_format={"type": "text", "mime_type": "application/json", "schema": schema},
        generation_config={"thinking_level": thinking_level, "max_output_tokens": max_output_tokens},
        store=False,
        timeout=timeout,
    )
    return interaction.output_text or ""


def parse_json(raw: str, what: str) -> dict:
    """The JSON object in raw. Tolerates a ```json fence or a line of text
    around it, which Gemma sometimes adds."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        value = json.loads(m.group(0) if m else raw or "")
    except json.JSONDecodeError as err:
        raise gemini.GeminiUnavailable(f"{config.LLM_NAME} returned {what} that isn't valid JSON: {err}") from err
    if not isinstance(value, dict):
        raise gemini.GeminiUnavailable(f"{config.LLM_NAME} returned {what} that isn't a JSON object.")
    return value
