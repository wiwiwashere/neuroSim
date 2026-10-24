"""The agent loop (CS2), using Gemini function calling through the google-genai
SDK's Interactions API.

The model asks for tool calls, we run them locally and send the results back,
until it answers in text. The server keeps the conversation, so we only pass
the previous interaction id, not the whole history. We record every tool call
so the UI can show "the agent ran these experiments" next to the answer.

Credentials: the SDK reads GEMINI_API_KEY. Model and thinking level come from
config.py.

TODO (CS2):
  * pull run ids out of run_simulation results into run_ids
  * when a tool raises, send {"error": "..."} as its result instead of crashing,
    so the model can explain the problem
  * on a 429 (free-tier rate limit), wait the suggested time and retry once,
    then retry with config.AGENT_FALLBACK_MODEL
  * check how the API wants several function calls in one step answered (we
    send all results together, matched by call_id)
"""

from __future__ import annotations

import json

from google import genai

from neurosim import config
from neurosim.agent.prompts import SYSTEM_PROMPT
from neurosim.agent.tools import TOOL_DECLARATIONS, TOOLS

_client: genai.Client | None = None
MAX_TOOL_ROUNDS = 8


def _get_client() -> genai.Client:
    # Created on first use so importing this module never needs credentials.
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def _create(input, previous_interaction_id: str | None):
    return _get_client().interactions.create(
        model=config.AGENT_MODEL,
        input=input,
        tools=TOOL_DECLARATIONS,
        system_instruction=SYSTEM_PROMPT,
        generation_config={
            "thinking_level": config.AGENT_THINKING_LEVEL,
            "max_output_tokens": config.AGENT_MAX_OUTPUT_TOKENS,
        },
        previous_interaction_id=previous_interaction_id,
    )


def chat(message: str, previous_interaction_id: str | None = None) -> dict:
    """Run one user turn.

    message: the user's latest message.
    previous_interaction_id: the interaction_id returned by the last turn, or
    None to start a new conversation.

    Returns {"reply", "tool_calls": [{"name", "arguments"}...], "run_ids",
             "interaction_id"} for the frontend.
    """
    interaction = _create(message, previous_interaction_id)
    tool_calls: list[dict] = []
    run_ids: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        calls = [s for s in interaction.steps if s.type == "function_call"]
        if not calls:
            break
        results = []
        for call in calls:
            args = call.arguments or {}
            tool_calls.append({"name": call.name, "arguments": args})
            output = TOOLS[call.name](**args)
            results.append(
                {
                    "type": "function_result",
                    "call_id": call.id,
                    "result": [{"type": "text", "text": output if isinstance(output, str) else json.dumps(output)}],
                }
            )
        interaction = _create(results, interaction.id)

    return {
        "reply": interaction.output_text,
        "tool_calls": tool_calls,
        "run_ids": run_ids,
        "interaction_id": interaction.id,
    }
