"""Tool-call parsing and argument coercion (CONTRACT.md §5, §1.2, §1.3).

``parse_tool_call`` answers the loop's central question — *given a model
response, what did the model just do?* — with a closed three-variant result:

- :class:`ToolCallRequest` — a valid call to an enabled tool, arguments
  already coerced against the tool's JSON schema
- :class:`FinalAnswer` — no tool call; the content is the answer (§5 step 4)
- :class:`RepairableError` — a well-formed call that is wrong (unknown tool,
  invalid/missing/uncoercible arguments); its ``message`` is fed back to the
  model as the tool result in §5's repair loop

The loop (E1.4) routes on these types alone — never on strings.

The §5 boundary kept sharp here: *unparseable* content (including a ```json
fence whose body is not valid JSON) is a final answer; *parseable but wrong*
is a repairable error.

No HTTP, no client dependency: inputs are response messages (E1.1's
``ChatMessage`` or the equivalent plain dict) and tool definitions in Ollama
wire format.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

# Machine-readable reason kinds for RepairableError.
UNKNOWN_TOOL = "unknown_tool"
INVALID_ARGUMENTS = "invalid_arguments"


@dataclass
class ToolCallRequest:
    """A valid call to an enabled tool; ``arguments`` are post-coercion."""

    name: str
    arguments: Dict[str, Any]


@dataclass
class FinalAnswer:
    """No tool call — ``content`` is the model's terminating answer."""

    content: str


@dataclass
class RepairableError:
    """A parseable-but-wrong call. ``message`` is model-facing (becomes the
    tool result in the §5 repair loop); ``kind`` is machine-readable
    (``unknown_tool`` | ``invalid_arguments``)."""

    message: str
    kind: str


ParseResult = Union[ToolCallRequest, FinalAnswer, RepairableError]


class ArgumentCoercionError(ValueError):
    """Raised by :func:`coerce_arguments` for invalid, missing, or
    uncoercible arguments. ``str(exc)`` is the model-facing message;
    ``parse_tool_call`` converts it to ``RepairableError(invalid_arguments)``.
    """


# ---------------------------------------------------------------------------
# Argument coercion (§1.3)
# ---------------------------------------------------------------------------

_TRUE_STRINGS = {"true"}
_FALSE_STRINGS = {"false"}


def coerce_arguments(
    arguments: Dict[str, Any], json_schema: Dict[str, Any]
) -> Dict[str, Any]:
    """Coerce mistyped primitive arguments against a flat JSON schema.

    Observed defect (§1.3): llama3.1 serializes integers as strings
    (``"8"``). Coercions applied: string→integer, string→number,
    string→boolean (``"true"``/``"false"``, case-insensitive). Correct types
    pass through unchanged; ``string`` properties are never coerced.
    Properties absent from the schema pass through untouched.

    Raises:
        ArgumentCoercionError: a required property is missing, or a value is
            uncoercible to its declared type.
    """
    properties = json_schema.get("properties") or {}
    required = json_schema.get("required") or []

    missing = [name for name in required if name not in arguments]
    if missing:
        raise ArgumentCoercionError(
            "missing required argument(s): "
            + ", ".join(repr(name) for name in missing)
            + ". Provide every required argument listed in the tool's schema."
        )

    coerced: Dict[str, Any] = {}
    for name, value in arguments.items():
        prop_schema = properties.get(name)
        if not isinstance(prop_schema, dict):
            coerced[name] = value  # not in schema — the tool handler decides
            continue
        coerced[name] = _coerce_value(name, value, prop_schema.get("type"))
    return coerced


def _coerce_value(name: str, value: Any, declared_type: Optional[str]) -> Any:
    if declared_type == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                pass
        raise ArgumentCoercionError(
            f"argument {name!r} must be an integer, got {value!r}. "
            f"Pass a whole number, e.g. 8."
        )
    if declared_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                pass
        raise ArgumentCoercionError(
            f"argument {name!r} must be a number, got {value!r}. "
            f"Pass a numeric value, e.g. 1.5."
        )
    if declared_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUE_STRINGS:
                return True
            if lowered in _FALSE_STRINGS:
                return False
        raise ArgumentCoercionError(
            f"argument {name!r} must be a boolean, got {value!r}. "
            f"Pass true or false."
        )
    if declared_type == "string":
        if isinstance(value, str):
            return value
        raise ArgumentCoercionError(
            f"argument {name!r} must be a string, got {value!r}."
        )
    # Untyped or non-primitive declared type: out of M1's flat-primitive
    # coercion scope — pass through untouched.
    return value


# ---------------------------------------------------------------------------
# parse_tool_call (§5)
# ---------------------------------------------------------------------------

_JSON_FENCE = re.compile(r"```json\s*\n?(.*?)```", re.DOTALL)


def parse_tool_call(
    message: Any, tools: List[Dict[str, Any]]
) -> ParseResult:
    """Classify a model response message per CONTRACT.md §5.

    ``message`` is E1.1's ``ChatMessage`` or the equivalent plain dict;
    ``tools`` are enabled tool definitions in Ollama wire format (the same
    dicts ``chat(tools=...)`` accepts).

    1. ``message.tool_calls`` non-empty → the **first** call (first-only for
       M1), content untouched.
    2. Else scan ``message.content`` for a ```json fence (prose around it is
       fine) or a bare ``{"name": ..., "arguments": {...}}`` object as the
       whole stripped content.
    3. Validate the name against enabled tools; coerce arguments to the
       tool's schema.
    4. Nothing parseable → ``FinalAnswer(content)``.
    """
    tool_calls, content = _message_fields(message)

    if tool_calls:
        native = tool_calls[0]
        function = native.get("function") or {}
        name = function.get("name") or ""
        arguments = function.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        return _validate_call(name, arguments, tools)

    extracted = _extract_call_from_content(content)
    if extracted is None:
        return FinalAnswer(content)
    name, arguments = extracted
    return _validate_call(name, arguments, tools)


def _message_fields(message: Any) -> "tuple[List[Dict[str, Any]], str]":
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
        content = message.get("content", "")
    else:  # ChatMessage or any object with the same attributes
        tool_calls = getattr(message, "tool_calls", None)
        content = getattr(message, "content", "")
    return list(tool_calls or []), content or ""


def _extract_call_from_content(
    content: str,
) -> "Optional[tuple[str, Dict[str, Any]]]":
    """Return ``(name, arguments)`` if the content carries a tool call in
    one of the two §1.2 content forms, else ``None`` (→ final answer)."""
    fence = _JSON_FENCE.search(content)
    candidate = fence.group(1) if fence else content.strip()
    if not candidate:
        return None
    try:
        parsed = json.loads(candidate)
    except ValueError:
        return None  # unparseable text is an answer, not an error (§5 step 4)
    if (
        isinstance(parsed, dict)
        and isinstance(parsed.get("name"), str)
        and isinstance(parsed.get("arguments"), dict)
    ):
        return parsed["name"], parsed["arguments"]
    return None


def _validate_call(
    name: str, arguments: Dict[str, Any], tools: List[Dict[str, Any]]
) -> ParseResult:
    schemas = _schemas_by_name(tools)
    if name not in schemas:
        enabled = ", ".join(sorted(schemas)) or "(none)"
        return RepairableError(
            message=(
                f"unknown tool {name!r}. "
                f"The enabled tools are: {enabled}."
            ),
            kind=UNKNOWN_TOOL,
        )
    try:
        coerced = coerce_arguments(arguments, schemas[name])
    except ArgumentCoercionError as exc:
        return RepairableError(
            message=f"invalid arguments for tool {name!r}: {exc}",
            kind=INVALID_ARGUMENTS,
        )
    return ToolCallRequest(name=name, arguments=coerced)


def _schemas_by_name(tools: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    schemas: Dict[str, Dict[str, Any]] = {}
    for tool in tools:
        function = tool.get("function") or {}
        name = function.get("name")
        if name:
            schemas[name] = function.get("parameters") or {}
    return schemas
