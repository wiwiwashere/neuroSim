"""The agent loop (CS2), using the Anthropic Python SDK's tool runner.

The tool runner calls our tools and feeds results back until the model is
done, so there is no hand-written loop. We record every tool call so the UI
can show "the agent ran these experiments" next to the answer.

Credentials: the SDK reads ANTHROPIC_API_KEY (or an `ant auth login` profile).
Model and effort come from config.py.
"""

from __future__ import annotations

import anthropic

from neurosim import config
from neurosim.agent.prompts import SYSTEM_PROMPT
from neurosim.agent.tools import ALL_TOOLS

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    # Created on first use so importing this module never needs credentials.
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def chat(messages: list[dict]) -> dict:
    """Run one user turn.

    messages: the conversation so far, in Messages API format, ending with
    the user's latest message.

    Returns {"reply": final text, "tool_calls": [{"name", "input"}...],
             "run_ids": [...]} for the frontend.

    TODO (CS2):
      * collect tool_use blocks from each message the runner yields
      * pull run ids out of run_simulation results
      * return the final message's text blocks joined
      * check stop_reason == "refusal" before reading content, and show a
        plain error instead of an empty reply
    """
    runner = _get_client().beta.messages.tool_runner(
        model=config.AGENT_MODEL,
        max_tokens=config.AGENT_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        messages=messages,
        output_config={"effort": config.AGENT_EFFORT},
        # Server-side fallback: if a safety classifier declines a request,
        # the API retries on a suitable model instead of returning a refusal.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    for message in runner:
        _ = message  # TODO: record tool calls and keep the last message
    raise NotImplementedError
