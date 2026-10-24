"""The agent loop (CS2): the model asks for tool calls, we run them locally and
send the results back, until it answers in text. We record every tool call so
the UI can show "the agent ran these experiments" next to the answer, and
return the run ids it made so the UI can load them into the main views.

Two model families (config.LLM) keep the conversation differently:
- Gemini, through the google-genai SDK's Interactions API: the server keeps
  the conversation, so we only pass the previous interaction id.
- Gemma, through generate_content (agent/gemma.py): we keep the history here,
  in memory, under an id of our own that the frontend passes back the same way.

Credentials: the SDK reads GEMINI_API_KEY from the environment (it serves
both families); config.py loads it from the repo-root .env. Models, thinking
level and the rate-limit fallback come from config.py (see agent/gemini.py
for the guards).
"""

from __future__ import annotations

import json
import time
import uuid

from google.genai import types

from neurosim import config
from neurosim.agent import gemini, gemma
from neurosim.agent.prompts import SYSTEM_PROMPT
from neurosim.agent.tools import TOOL_DECLARATIONS, TOOLS

# Gemma conversations: our id -> the contents so far. Restarting the API
# drops them, and the next message starts a new conversation.
_HISTORY: dict[str, list[types.Content]] = {}
_MAX_CONVERSATIONS = 200


def _too_slow() -> gemini.GeminiUnavailable:
    s = config.AGENT_TURN_DEADLINE_S
    limit = f"{s / 60:g} minute{'s' if s != 60 else ''}" if s % 60 == 0 else f"{s:g} seconds"
    return gemini.GeminiUnavailable(
        f"The agent couldn't finish within {limit} because {config.LLM_NAME} is slow right now. Try again in a minute."
    )


def _create(input, previous_interaction_id: str | None, state: dict, deadline: float, tool_choice: str = "auto"):
    """One Gemini Interactions call, given only the time left before the turn's deadline."""

    def create(model: str):
        left = deadline - time.monotonic()
        if left <= 0:
            raise _too_slow()
        return gemini.client().interactions.create(
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
            timeout=min(config.AGENT_REQUEST_TIMEOUT_S, left),
        )

    return gemini.call(create, state)


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


class _GeminiTurn:
    """The server keeps the conversation; we carry the interaction id."""

    def __init__(self, previous_id: str | None, state: dict, deadline: float):
        # An id from a Gemma conversation means nothing to the server.
        self.id = None if previous_id and previous_id.startswith("gemma-") else previous_id
        self.state, self.deadline = state, deadline

    def send(self, input, tool_choice: str = "auto") -> tuple[list, str]:
        """Returns ([(call_id, name, args)...], answer text)."""
        interaction = _create(input, self.id, self.state, self.deadline, tool_choice)
        self.id = interaction.id
        calls = [(s.id, s.name, s.arguments or {}) for s in interaction.steps or [] if s.type == "function_call"]
        return calls, interaction.output_text or ""

    def results(self, done: list[tuple]) -> list[dict]:
        return [
            {"type": "function_result", "call_id": call_id, "name": name, "is_error": is_error,
             "result": [{"type": "text", "text": output}]}
            for call_id, name, output, is_error in done
        ]

    def finish(self) -> str:
        return self.id


class _GemmaTurn:
    """We keep the history and send all of it with every call."""

    def __init__(self, previous_id: str | None, state: dict, deadline: float):
        self.history = list(_HISTORY.get(previous_id or "", []))
        self.state, self.deadline = state, deadline

    def send(self, input, tool_choice: str = "auto") -> tuple[list, str]:
        if isinstance(input, str):
            input = types.Content(role="user", parts=[types.Part(text=input)])
        self.history.append(input)

        def create(model: str):
            left = self.deadline - time.monotonic()
            if left <= 0:
                raise _too_slow()
            cfg = gemma.generation_config(
                SYSTEM_PROMPT,
                thinking_level=config.AGENT_THINKING_LEVEL,
                max_output_tokens=config.AGENT_MAX_OUTPUT_TOKENS,
                timeout=min(config.AGENT_REQUEST_TIMEOUT_S, left),
                tools=gemma.function_tools(),
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="NONE" if tool_choice == "none" else "AUTO")
                ),
            )
            return gemma.generate(model, self.history, cfg)

        response = gemini.call(create, self.state)
        reply = gemma.content(response)
        self.history.append(reply)
        calls = [(p.function_call.id, p.function_call.name, dict(p.function_call.args or {}))
                 for p in reply.parts or [] if p.function_call]
        return calls, gemma.text(response)

    def results(self, done: list[tuple]) -> types.Content:
        return types.Content(role="user", parts=[
            # Errors are already {"error": ...}; anything else goes under "result".
            types.Part(function_response=types.FunctionResponse(
                id=call_id, name=name, response=json.loads(output) if is_error else {"result": json.loads(output)}))
            for call_id, name, output, is_error in done
        ])

    def finish(self) -> str:
        conversation_id = f"gemma-{uuid.uuid4().hex[:16]}"
        _HISTORY[conversation_id] = self.history
        while len(_HISTORY) > _MAX_CONVERSATIONS:
            _HISTORY.pop(next(iter(_HISTORY)))
        return conversation_id


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
    # Every call and tool round shares one deadline, so a slow model ends the
    # turn with a readable 503 instead of outlasting the frontend proxy.
    deadline = time.monotonic() + config.AGENT_TURN_DEADLINE_S
    turn = (_GemmaTurn if config.LLM == "gemma" else _GeminiTurn)(previous_interaction_id, state, deadline)
    calls, reply = turn.send(_with_context(message, context))
    tool_calls: list[dict] = []
    run_ids: list[str] = []

    for round_ in range(config.AGENT_MAX_TOOL_ROUNDS):
        if not calls:
            break
        done = []
        for call_id, name, args in calls:
            output, is_error = _run_tool(name, args)
            tool_calls.append({"name": name, "arguments": args, "error": json.loads(output)["error"] if is_error else None})
            if name == "run_simulation" and not is_error:
                run_id = json.loads(output)["run_id"]
                if run_id not in run_ids:
                    run_ids.append(run_id)
            done.append((call_id, name, output, is_error))
        # Out of rounds: hand back the last results and make it answer in text.
        last = round_ == config.AGENT_MAX_TOOL_ROUNDS - 1
        calls, reply = turn.send(turn.results(done), tool_choice="none" if last else "auto")

    return {
        "reply": reply,
        "tool_calls": tool_calls,
        "run_ids": run_ids,
        "interaction_id": turn.finish(),
        "model": state.get("model", config.AGENT_MODEL),
    }
