"""The §5 execution loop, §3 Result and transcript (CONTRACT.md §3, §5, §6).

Wires E1.1–E1.3 together: ``chat → parse_tool_call → execute_tool → feed
back`` until the model produces a final answer or the iteration ceiling
halts it. The loop routes on E1.2's closed three-variant parse result and
nothing else — no permission logic, no parsing logic, no tool logic here.

Repair, don't crash (§5): every repairable condition — unknown tool,
invalid/uncoercible arguments (the loop-visible form of a malformed call;
E1.2 classifies *unparseable* content as a final answer), denied
permission, handler failure — is fed back to the model as a ``role:
"tool"`` message, bounded by ``max_iterations``.

Deterministic termination: a turn with no tool call is the final answer
(``completed``); loop exhaustion is ``max_iterations_exceeded``; a client
failure mid-run is ``error`` with the accumulated transcript preserved.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from local_agent_runner.ollama_client import (
    DEFAULT_ENDPOINT,
    ChatMessage,
    OllamaClient,
    OllamaClientError,
)
from local_agent_runner.tool_calls import (
    FinalAnswer,
    ToolCallRequest,
    parse_tool_call,
)
from local_agent_runner.tools import (
    ToolPermissions,
    execute_tool,
    tool_definitions,
)

DEFAULT_MAX_ITERATIONS = 10

STATUS_COMPLETED = "completed"
STATUS_MAX_ITERATIONS_EXCEEDED = "max_iterations_exceeded"
STATUS_ERROR = "error"


@dataclass
class Result:
    """Outcome of one run (CONTRACT.md §3).

    ``transcript`` holds one step per tool round (executed call *or* repair
    round): ``{"tool_call": {"name", "args"}, "tool_result", "ms",
    "eval_count"}``. ``iterations`` is the number of tool rounds (=
    transcript length); ``tokens`` is the total ``eval_count`` over all
    model turns including the final one (``None`` counted as 0).

    ``error`` carries the failure reason when ``status == "error"``; it is
    deliberately **not** part of :meth:`to_dict` — the §3 shape is exactly
    seven fields, and the CLI surfaces the reason on stderr instead.
    """

    status: str
    final_answer: Optional[str]
    transcript: List[Dict[str, Any]]
    iterations: int
    tokens: int
    model: str
    duration_ms: int
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """The exact §3 JSON shape — seven fields, nothing else."""
        return {
            "status": self.status,
            "final_answer": self.final_answer,
            "transcript": self.transcript,
            "iterations": self.iterations,
            "tokens": self.tokens,
            "model": self.model,
            "duration_ms": self.duration_ms,
        }


def run(
    model: str,
    task: str,
    permissions: ToolPermissions,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    system: Optional[str] = None,
    context: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    client: Optional[OllamaClient] = None,
) -> Result:
    """Run the §5 loop and return the §3 Result.

    ``client`` is injectable for offline tests; when ``None`` a real
    :class:`OllamaClient` is built for ``endpoint``. ``system`` and
    ``context`` seed optional leading messages per §5 (``context`` as a
    system-role message); the CLI does not surface them in M1.
    """
    if client is None:
        client = OllamaClient(endpoint)
    tools = tool_definitions(permissions)

    messages: List[Union[ChatMessage, Dict[str, Any]]] = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    if context is not None:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": task})

    transcript: List[Dict[str, Any]] = []
    tokens = 0
    start = time.monotonic()

    def result(
        status: str,
        final_answer: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Result:
        return Result(
            status=status,
            final_answer=final_answer,
            transcript=transcript,
            iterations=len(transcript),
            tokens=tokens,
            model=model,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=error,
        )

    for _ in range(max_iterations):
        round_start = time.monotonic()
        try:
            response = client.chat(model, messages, tools=tools, options=options)
        except OllamaClientError as exc:
            # No partial crash — whatever transcript accumulated is preserved.
            return result(STATUS_ERROR, error=str(exc))
        tokens += response.eval_count or 0

        parsed = parse_tool_call(response.message, tools)
        if isinstance(parsed, FinalAnswer):
            return result(STATUS_COMPLETED, final_answer=parsed.content)

        if isinstance(parsed, ToolCallRequest):
            feedback = execute_tool(
                parsed.name, parsed.arguments, permissions
            ).output  # ok or not — a tool-level error is repair feedback (§5)
            name, args = parsed.name, parsed.arguments
        else:  # RepairableError
            feedback = parsed.message
            name, args = _attempted_call(response.message)

        # The model must see its own prior turn the way it emitted it:
        # native tool_calls intact, or content JSON as content.
        messages.append(response.message)
        messages.append({"role": "tool", "content": feedback})
        transcript.append(
            {
                "tool_call": {"name": name, "args": args},
                "tool_result": feedback,
                "ms": int((time.monotonic() - round_start) * 1000),
                "eval_count": response.eval_count,
            }
        )

    return result(STATUS_MAX_ITERATIONS_EXCEEDED)


# E1.2 does not expose the attempted call on RepairableError, so the
# transcript's repair steps recover it here — mirrors the §1.2 delivery
# modes, performs no validation (classification stays in E1.2).
_JSON_FENCE = re.compile(r"```json\s*\n?(.*?)```", re.DOTALL)


def _attempted_call(message: Any) -> Tuple[str, Dict[str, Any]]:
    """Best-effort ``(name, args)`` of what the model attempted, for a
    repair round's transcript step (the unknown tool's name, the
    uncoercible arguments)."""
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        function = tool_calls[0].get("function") or {}
        name = function.get("name")
        args = function.get("arguments")
    else:
        content = getattr(message, "content", "") or ""
        fence = _JSON_FENCE.search(content)
        candidate = fence.group(1) if fence else content.strip()
        try:
            parsed = json.loads(candidate)
        except ValueError:
            return "", {}
        if not isinstance(parsed, dict):
            return "", {}
        name = parsed.get("name")
        args = parsed.get("arguments")
    return (
        name if isinstance(name, str) else "",
        args if isinstance(args, dict) else {},
    )
