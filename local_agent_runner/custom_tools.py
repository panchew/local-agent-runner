"""Pluggable custom tool handlers for the library API (CONTRACT.md §2, §4, §10.1).

The CLI exposes only the vetted built-in library (§4). Library callers can
also register **in-process** tools: plain Python functions that sit next to
the built-ins in the same §5 loop, with the same parsing, §1.3 coercion and
repair-don't-crash behavior.

    from local_agent_runner import ToolPermissions, custom_tool, run

    @custom_tool
    def hello_world(name: str) -> str:
        \"\"\"Greet someone by name. Pass 'name' as the person to greet.\"\"\"
        return f"Hello, {name}!"

    result = run("qwen2.5-coder:14b", "Greet Ada.", ToolPermissions(),
                 custom_tools=[hello_world])

``@custom_tool`` derives the tool from the function:

- **name**: the function name (or ``name=``)
- **description**: the docstring (or ``description=``). It's required,
  because a local model picks tools by their description.
- **parameters**: a flat JSON schema built from the signature. ``str`` /
  ``int`` / ``float`` / ``bool`` map to ``string`` / ``integer`` /
  ``number`` / ``boolean`` (the §1.3 coercion scope). Parameters without a
  default are ``required``. Pass ``parameters=`` to supply the schema
  yourself (e.g. to add per-argument descriptions).

The decorated object is still directly callable, so the tool can be unit
tested as a normal function.

Handlers are called as ``handler(**arguments)`` and may return:

- a ``str``, which becomes the tool result
- a :class:`~local_agent_runner.tools.ToolResult`, passed through as is
- anything else, which is JSON-encoded

Handler exceptions never escape. They become model-facing error results,
the same as for the built-ins (§5).

Enabling a custom tool means passing it to ``run()``. It doesn't need to be
listed in ``ToolPermissions.enabled``, and ``ToolPermissions`` doesn't apply
to it. A custom handler runs with the caller's full privileges, so its
scoping is the caller's responsibility.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
import typing
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional

from local_agent_runner.tools import _MSG_UNEXPECTED, _TOOL_ORDER, ToolResult

# Ollama / OpenAI function-name shape.
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass(frozen=True)
class CustomTool:
    """One in-process tool: wire-format metadata plus its Python handler."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME_PATTERN.match(self.name):
            raise ValueError(
                f"invalid custom tool name {self.name!r}: use 1-64 letters, "
                "digits, '_' or '-'"
            )
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError(
                f"custom tool {self.name!r} needs a non-empty description "
                "(the model chooses tools by their description)"
            )
        if not isinstance(self.parameters, dict) or self.parameters.get("type") != "object":
            raise ValueError(
                f"custom tool {self.name!r}: parameters must be a JSON schema "
                'object ({"type": "object", "properties": {...}})'
            )
        if not callable(self.handler):
            raise TypeError(f"custom tool {self.name!r}: handler is not callable")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the underlying function directly (handy for unit tests)."""
        return self.handler(*args, **kwargs)

    def definition(self) -> Dict[str, Any]:
        """The Ollama wire-format definition, the same shape as the built-ins."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": copy.deepcopy(self.parameters),
            },
        }


def custom_tool(
    func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Any:
    """Decorator that turns a typed function into a :class:`CustomTool`.

    Works bare (``@custom_tool``) or with overrides
    (``@custom_tool(name=..., description=..., parameters=...)``).
    Signature problems raise at decoration time, not mid-run.
    """

    def wrap(fn: Callable[..., Any]) -> CustomTool:
        return CustomTool(
            name=name or fn.__name__,
            description=description or inspect.cleandoc(fn.__doc__ or ""),
            parameters=parameters if parameters is not None else _infer_schema(fn),
            handler=fn,
        )

    return wrap(func) if func is not None else wrap


def _infer_schema(fn: Callable[..., Any]) -> Dict[str, Any]:
    hints = typing.get_type_hints(fn)  # resolves `from __future__ import annotations`
    properties: Dict[str, Any] = {}
    required = []
    for param in inspect.signature(fn).parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD, param.POSITIONAL_ONLY):
            raise TypeError(
                f"custom tool {fn.__name__!r}: parameter {param.name!r} must be "
                "passable by keyword (no *args, **kwargs or positional-only)"
            )
        json_type = _JSON_TYPES.get(hints.get(param.name))  # type: ignore[arg-type]
        if json_type is None:
            raise TypeError(
                f"custom tool {fn.__name__!r}: parameter {param.name!r} must be "
                "annotated as str, int, float or bool, or pass parameters= "
                "explicitly"
            )
        properties[param.name] = {"type": json_type}
        if param.default is param.empty:
            required.append(param.name)
    return {"type": "object", "properties": properties, "required": required}


def index_custom_tools(tools: Optional[Iterable[CustomTool]]) -> Dict[str, CustomTool]:
    """Validate a caller's custom tools and index them by name. Raises
    ``ValueError`` on duplicates or on a name that shadows a built-in.
    Those are caller mistakes, so they surface before the loop starts."""
    indexed: Dict[str, CustomTool] = {}
    for item in tools or ():
        if not isinstance(item, CustomTool):
            raise TypeError(
                f"custom_tools entries must be CustomTool (use @custom_tool), "
                f"got {type(item).__name__}"
            )
        if item.name in _TOOL_ORDER:
            raise ValueError(
                f"custom tool name {item.name!r} collides with a built-in tool"
            )
        if item.name in indexed:
            raise ValueError(f"duplicate custom tool name {item.name!r}")
        indexed[item.name] = item
    return indexed


def execute_custom_tool(tool: CustomTool, arguments: Dict[str, Any]) -> ToolResult:
    """Run a custom handler. Never raises: any exception (including a
    ``TypeError`` for unexpected arguments) becomes a model-facing error
    result for the §5 repair loop."""
    try:
        value = tool.handler(**arguments)
        if isinstance(value, ToolResult):
            return value
        if isinstance(value, str):
            return ToolResult(ok=True, output=value)
        return ToolResult(ok=True, output=json.dumps(value, default=str))
    except Exception as exc:  # noqa: BLE001 (never-raising surface, §5)
        return ToolResult(
            ok=False,
            output=_MSG_UNEXPECTED.format(
                tool=tool.name, kind=type(exc).__name__, detail=exc
            ),
        )
