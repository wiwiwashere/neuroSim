"""The agent loop (CS2), using Gemini function calling through the google-genai
SDK's Interactions API.

The model asks for tool calls, we run them locally and send the results back,
until it answers in text. The server keeps the conversation, so we only pass
the previous interaction id, not the whole history. We record every tool call
so the UI can show "the agent ran these experiments" next to the answer, and
return the run ids it made so the UI can load them into the main views.

Credentials: the SDK reads GEMINI_API_KEY from the environment; config.py
loads it from the repo-root .env. Model, thinking level and the rate-limit
fallback come from config.py (see agent/gemini.py for the guards).
"""

from __future__ import annotations

import json

from neurosim import config
from neurosim.agent import gemini
from neurosim.agent.prompts import SYSTEM_PROMPT
from neurosim.agent.tools import TOOL_DECLARATIONS, TOOLS


def _create(input, previous_interaction_id: str | None, state: dict, tool_choice: str = "auto"):
    return gemini.call(
        lambda model: gemini.client().interactions.create(
            model=model,
            input=input,
            tools=TOOL_DECLARATIONS,
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                "thinking_level": config.AGENT_THINKING_LEVEL,
                "max_output_tokens": config.AGENT_MAX_OUTPUT_TOKENS,
                "tool_choice": tool_choice,
            },
            previous_interaction_id=previous_interaction_id,
            timeout=config.AGENT_REQUEST_TIMEOUT_S,
        ),
        state,
    )


def _with_context(message: str, context: dict | None) -> str:
    """Tell the model what is on screen, so "what if they lose half?" has a subject."""
    run = (context or {}).get("active_run")
    if not run:
        return message
    return (
        f"[Workspace context, not typed by the user: the results view shows run {run.get('run_id')} "
        f"({json.dumps({k: v for k, v in run.items() if k != 'run_id'})}).]\n\n{message}"
    )


def _run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Returns (result text, is_error). Errors go back to the model as results
    so it can explain them instead of the turn crashing."""
    fn = TOOLS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool {name}."}), True
    try:
        output = fn(**args)
    except (ValueError, KeyError, TypeError, NotImplementedError) as err:
        return json.dumps({"error": str(err) or type(err).__name__}), True
    return output if isinstance(output, str) else json.dumps(output), False


def chat(message: str, previous_interaction_id: str | None = None, context: dict | None = None) -> dict:
    """Run one user turn.

    message: the user's latest message.
    previous_interaction_id: the interaction_id returned by the last turn, or
    None to start a new conversation.
    context: what the workspace shows, {"active_run": {...}} or None.

    Returns {"reply", "tool_calls": [{"name", "arguments", "error"}...], "run_ids",
             "interaction_id", "model"} for the frontend.
    """
    state: dict = {}
    interaction = _create(_with_context(message, context), previous_interaction_id, state)
    tool_calls: list[dict] = []
    run_ids: list[str] = []

    for round_ in range(config.AGENT_MAX_TOOL_ROUNDS):
        calls = [s for s in interaction.steps or [] if s.type == "function_call"]
        if not calls:
            break
        results = []
        for call in calls:
            args = call.arguments or {}
            output, is_error = _run_tool(call.name, args)
            tool_calls.append({"name": call.name, "arguments": args, "error": json.loads(output)["error"] if is_error else None})
            if call.name == "run_simulation" and not is_error:
                run_id = json.loads(output)["run_id"]
                if run_id not in run_ids:
                    run_ids.append(run_id)
            results.append(
                {
                    "type": "function_result",
                    "call_id": call.id,
                    "name": call.name,
                    "is_error": is_error,
                    "result": [{"type": "text", "text": output}],
                }
            )
        # Out of rounds: hand back the last results and make it answer in text.
        last = round_ == config.AGENT_MAX_TOOL_ROUNDS - 1
        interaction = _create(results, interaction.id, state, tool_choice="none" if last else "auto")

    return {
        "reply": interaction.output_text or "",
        "tool_calls": tool_calls,
        "run_ids": run_ids,
        "interaction_id": interaction.id,
        "model": state.get("model", config.AGENT_MODEL),
    }
