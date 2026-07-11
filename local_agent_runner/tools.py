"""Proof tools and permission scoping (CONTRACT.md §4, §5, §6, §9).

Delivers the three §9 proof tools — ``read_file``, ``edit_file``,
``run_command`` — plus ``write_file`` and ``list_dir`` (E2.1) and ``git``
(E2.2), behind a single never-raising execution surface:

    execute_tool(name, arguments, permissions) -> ToolResult(ok, output)

``output`` is exactly the text E1.4 feeds back to the model as the tool
result. Every expected failure (denied path, missing file, ambiguous edit,
denied command, denied subcommand, timeout) and every unexpected handler
exception becomes a deterministic, model-facing error result — the §5
repair loop's input. Denial messages are built from module-level templates
so the same denial always yields the same bytes (§4 determinism by
construction).

Permissions follow the §4 ``tools.json`` shape via
:meth:`ToolPermissions.from_dict` (file I/O stays in E1.4). All list-valued
knobs deny by default: no ``allow_paths`` → all paths denied; no
``allow_commands`` → all commands denied; no ``allow_subcommands`` → all
git subcommands denied; ``deny_commands`` wins over ``allow_commands``.
Paths are matched as **resolved absolute paths** (symlinks and ``..``
resolved first), so traversal cannot escape the allowed globs.

``run_command`` uses ``subprocess.run`` with ``shell=True`` and an enforced
timeout (spec-settled); a non-zero exit code is a *successful* tool result —
a failing test is information for the model, not a tool failure. ``git``
uses the same timeout knob but always runs with ``shell=False`` (a literal
argv list, no shell-injection surface), gated by ``allow_subcommands``
matched exactly against the first parsed token of ``args``. Stdout and
stderr are each capped at :data:`OUTPUT_CAP` characters (§6 token
discipline).
"""

from __future__ import annotations

import copy
import shlex
import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, List, Union

# §4 example uses 120; applied when tools.json omits "timeout".
DEFAULT_COMMAND_TIMEOUT: Union[int, float] = 120
# Cap per stream (stdout, stderr) in run_command output — §6 token discipline.
OUTPUT_CAP = 4000

# ---------------------------------------------------------------------------
# Model-facing message templates (module-level: determinism by construction).
# Same denial → same message, byte for byte.
# ---------------------------------------------------------------------------

_NO_GLOBS = "(none - no paths are permitted)"
_NO_PATTERNS = "(none - no commands are permitted)"

_MSG_PATH_DENIED = (
    "{tool}: access to path '{path}' is denied. "
    "Only paths matching these allow_paths globs are permitted: {globs}"
)
_MSG_FILE_MISSING = (
    "{tool}: file '{path}' does not exist. "
    "Provide the path of an existing file."
)
_MSG_NOT_A_FILE = (
    "{tool}: path '{path}' is not a regular file. "
    "Provide the path of a text file."
)
_MSG_IS_A_DIRECTORY = (
    "write_file: path '{path}' is a directory. "
    "Provide the path of a file to create or overwrite."
)
_MSG_DIR_MISSING = (
    "list_dir: directory '{path}' does not exist. "
    "Provide the path of an existing directory."
)
_MSG_NOT_A_DIRECTORY = (
    "list_dir: path '{path}' is not a directory. "
    "Provide the path of a directory."
)
_MSG_DIR_EMPTY = "list_dir: '{path}' is empty."
_MSG_BAD_RANGE = (
    "read_file: invalid line range start_line={start}, end_line={end} for "
    "'{path}' ({lines} lines). Lines are 1-based and inclusive; start_line "
    "must be between 1 and the file's line count, and end_line must be >= "
    "start_line."
)
_MSG_OLD_NOT_FOUND = (
    "edit_file: 'old' text not found in '{path}'. "
    "Provide 'old' exactly as it appears in the file, including whitespace."
)
_MSG_OLD_AMBIGUOUS = (
    "edit_file: 'old' text occurs {count} times in '{path}' but must occur "
    "exactly once. Provide a longer 'old' string that uniquely identifies "
    "one location."
)
_MSG_COMMAND_DENIED = (
    "run_command: command '{command}' is denied. "
    "Only commands matching these allow_commands patterns are permitted "
    "(deny_commands patterns win): {patterns}"
)
_MSG_COMMAND_TIMEOUT = (
    "run_command: command '{command}' timed out after {timeout} seconds and "
    "was killed. Use a command that finishes within the timeout."
)
_NO_SUBCOMMANDS = "(none - no subcommands are permitted)"
_MSG_GIT_SUBCOMMAND_DENIED = (
    "git: subcommand '{subcommand}' is denied. "
    "Only these allow_subcommands are permitted: {subcommands}"
)
_MSG_GIT_NO_SUBCOMMAND = (
    "git: no subcommand provided in 'args'. "
    "Pass the subcommand first, e.g. 'status --short'."
)
_MSG_GIT_PARSE_ERROR = (
    "git: could not parse 'args' ({detail}). "
    "Check for unbalanced quotes."
)
_MSG_GIT_TIMEOUT = (
    "git: command 'git {args}' timed out after {timeout} seconds and "
    "was killed. Use a command that finishes within the timeout."
)
_MSG_UNKNOWN_TOOL = (
    "unknown tool '{name}'. Available tools: {available}."
)
_MSG_BAD_ARGUMENT = (
    "{tool}: argument {argument!r} must be a {expected}, got {value!r}."
)
_MSG_UNEXPECTED = (
    "{tool}: unexpected error while executing: {kind}: {detail}"
)

_TRUNCATION_MARKER = "\n[truncated: stream exceeded {cap} characters]"


@dataclass
class ToolResult:
    """Outcome of one tool execution. ``output`` is fed back to the model
    verbatim as the tool result; ``ok`` is False only for tool-level errors
    (a command's non-zero exit code is ``ok=True`` — see §9)."""

    ok: bool
    output: str


@dataclass
class ToolPermissions:
    """The §4 permission knobs the three proof tools need.

    Both knobs deny by default: an empty ``allow_paths`` denies every path;
    an empty ``allow_commands`` denies every command. ``deny_commands`` wins
    over ``allow_commands``.
    """

    enabled: List[str] = field(default_factory=list)
    allow_paths: List[str] = field(default_factory=list)
    allow_commands: List[str] = field(default_factory=list)
    deny_commands: List[str] = field(default_factory=list)
    allow_subcommands: List[str] = field(default_factory=list)
    timeout: Union[int, float] = DEFAULT_COMMAND_TIMEOUT

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolPermissions":
        """Build permissions from the §4 ``tools.json`` dict shape.
        Reading the file from disk is E1.4's job."""
        return cls(
            enabled=list(data.get("enabled") or []),
            allow_paths=list(data.get("allow_paths") or []),
            allow_commands=list(data.get("allow_commands") or []),
            deny_commands=list(data.get("deny_commands") or []),
            allow_subcommands=list(data.get("allow_subcommands") or []),
            timeout=data.get("timeout", DEFAULT_COMMAND_TIMEOUT),
        )

    def path_permitted(self, path: Union[str, Path]) -> bool:
        """True iff the **resolved absolute** path matches an allow glob.
        Symlinks and ``..`` are resolved first, so traversal cannot escape."""
        resolved = str(Path(path).resolve())
        return any(fnmatchcase(resolved, glob) for glob in self.allow_paths)

    def command_permitted(self, command: str) -> bool:
        """True iff the whole command string matches an allow pattern and no
        deny pattern (deny wins; empty allow list denies everything)."""
        if any(fnmatchcase(command, pat) for pat in self.deny_commands):
            return False
        return any(fnmatchcase(command, pat) for pat in self.allow_commands)

    def subcommand_permitted(self, name: str) -> bool:
        """True iff ``name`` exactly matches an entry in
        ``allow_subcommands`` (deny by default). Exact membership, not
        ``fnmatch`` — git subcommands are discrete tokens, not glob
        patterns."""
        return name in self.allow_subcommands


# ---------------------------------------------------------------------------
# Tool definitions (Ollama wire format — the dicts chat(tools=...) sends and
# parse_tool_call(tools=...) validates against). Flat primitive schemas only
# (E1.2's coercion scope); descriptions written for a local model.
# ---------------------------------------------------------------------------

_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a text file. Pass 'path' as the file's path. "
                "Optionally pass 'start_line' and 'end_line' (1-based, "
                "inclusive) to read only that line range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to read.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to read (1-based, inclusive).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to read (1-based, inclusive).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create a new file or overwrite an existing one. Pass "
                "'path' as the file's path and 'content' as the full text "
                "to write. Missing parent directories are created "
                "automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to create or overwrite.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    "edit_file": {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit a text file by exact replacement. Pass 'path', the "
                "exact existing text as 'old', and the replacement text as "
                "'new'. 'old' must occur exactly once in the file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to edit.",
                    },
                    "old": {
                        "type": "string",
                        "description": (
                            "Exact text to replace; must occur exactly once."
                        ),
                    },
                    "new": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    "list_dir": {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "List the immediate entries of a directory. Pass 'path' as "
                "the directory's path. Subdirectory entries are suffixed "
                "with '/'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the directory to list.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    "run_command": {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command and return its exit code, stdout, and "
                "stderr. Pass the full command as 'command', e.g. "
                "'pytest tests/test_x.py'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    "git": {
        "type": "function",
        "function": {
            "name": "git",
            "description": (
                "Run a git subcommand and return its exit code, stdout, and "
                "stderr. Pass the arguments as 'args', with the subcommand "
                "first (not including the leading 'git' itself), e.g. "
                "'status --short', 'add app.py', 'commit -m \"fix bug\"'. "
                "The subcommand must be one you have been permitted to use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": (
                            "The git arguments, subcommand first, e.g. "
                            "'status --short'."
                        ),
                    },
                },
                "required": ["args"],
            },
        },
    },
}

# Canonical exposure order for tool_definitions() (CONTRACT.md §4 table order).
_TOOL_ORDER = [
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "run_command",
    "git",
]


def tool_definitions(permissions: ToolPermissions) -> List[Dict[str, Any]]:
    """Wire-format definitions for the tools enabled in ``permissions``,
    in canonical order. Unknown names in ``enabled`` are ignored (E1.4
    decides whether to reject them at config time). Returns fresh copies —
    callers may mutate freely."""
    return [
        copy.deepcopy(_DEFINITIONS[name])
        for name in _TOOL_ORDER
        if name in permissions.enabled
    ]


# ---------------------------------------------------------------------------
# Handlers. Each returns a ToolResult and raises nothing on expected
# failures; execute_tool() converts anything unexpected.
# ---------------------------------------------------------------------------


def _error(template: str, **kwargs: Any) -> ToolResult:
    return ToolResult(ok=False, output=template.format(**kwargs))


def _globs_text(permissions: ToolPermissions) -> str:
    return ", ".join(permissions.allow_paths) or _NO_GLOBS


def _patterns_text(permissions: ToolPermissions) -> str:
    return ", ".join(permissions.allow_commands) or _NO_PATTERNS


def _subcommands_text(permissions: ToolPermissions) -> str:
    return ", ".join(sorted(permissions.allow_subcommands)) or _NO_SUBCOMMANDS


def _require_string(
    tool: str, arguments: Dict[str, Any], name: str
) -> "tuple[str, ToolResult]":
    """Return (value, None-like) or ('', error result) for a required
    string argument. E1.2's coercion normally guarantees these; this guards
    the public surface when execute_tool is called directly."""
    value = arguments.get(name)
    if not isinstance(value, str):
        return "", _error(
            _MSG_BAD_ARGUMENT,
            tool=tool,
            argument=name,
            expected="string",
            value=value,
        )
    return value, ToolResult(ok=True, output="")


def _checked_file(
    tool: str, path_arg: str, permissions: ToolPermissions
) -> "tuple[Path, ToolResult]":
    """Resolve and permission-check a file path shared by the file tools.
    Returns (resolved_path, ok-result) or (resolved_path, error result)."""
    resolved = Path(path_arg).resolve()
    if not permissions.path_permitted(resolved):
        return resolved, _error(
            _MSG_PATH_DENIED,
            tool=tool,
            path=resolved,
            globs=_globs_text(permissions),
        )
    if not resolved.exists():
        return resolved, _error(_MSG_FILE_MISSING, tool=tool, path=resolved)
    if not resolved.is_file():
        return resolved, _error(_MSG_NOT_A_FILE, tool=tool, path=resolved)
    return resolved, ToolResult(ok=True, output="")


def _read_file(
    arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    path_arg, check = _require_string("read_file", arguments, "path")
    if not check.ok:
        return check
    resolved, check = _checked_file("read_file", path_arg, permissions)
    if not check.ok:
        return check

    content = resolved.read_text()
    start = arguments.get("start_line")
    end = arguments.get("end_line")
    if start is None and end is None:
        return ToolResult(ok=True, output=content)

    lines = content.splitlines(keepends=True)
    start = 1 if start is None else start
    end = len(lines) if end is None else end
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or start < 1
        or start > len(lines)
        or end < start
    ):
        return _error(
            _MSG_BAD_RANGE,
            start=start,
            end=end,
            path=resolved,
            lines=len(lines),
        )
    return ToolResult(ok=True, output="".join(lines[start - 1 : end]))


def _edit_file(
    arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    for name in ("path", "old", "new"):
        _, check = _require_string("edit_file", arguments, name)
        if not check.ok:
            return check
    resolved, check = _checked_file(
        "edit_file", arguments["path"], permissions
    )
    if not check.ok:
        return check

    old, new = arguments["old"], arguments["new"]
    content = resolved.read_text()
    count = content.count(old)
    if count == 0:
        return _error(_MSG_OLD_NOT_FOUND, path=resolved)
    if count > 1:
        return _error(_MSG_OLD_AMBIGUOUS, count=count, path=resolved)
    resolved.write_text(content.replace(old, new))
    return ToolResult(
        ok=True,
        output=f"edit_file: replaced 1 occurrence in '{resolved}'.",
    )


def _write_file(
    arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    path_arg, check = _require_string("write_file", arguments, "path")
    if not check.ok:
        return check
    content, check = _require_string("write_file", arguments, "content")
    if not check.ok:
        return check

    resolved = Path(path_arg).resolve()
    if not permissions.path_permitted(resolved):
        return _error(
            _MSG_PATH_DENIED,
            tool="write_file",
            path=resolved,
            globs=_globs_text(permissions),
        )
    if resolved.exists() and resolved.is_dir():
        return _error(_MSG_IS_A_DIRECTORY, path=resolved)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)
    return ToolResult(
        ok=True,
        output=f"write_file: wrote {len(content)} characters to '{resolved}'.",
    )


def _list_dir(
    arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    path_arg, check = _require_string("list_dir", arguments, "path")
    if not check.ok:
        return check

    resolved = Path(path_arg).resolve()
    if not permissions.path_permitted(resolved):
        return _error(
            _MSG_PATH_DENIED,
            tool="list_dir",
            path=resolved,
            globs=_globs_text(permissions),
        )
    if not resolved.exists():
        return _error(_MSG_DIR_MISSING, path=resolved)
    if not resolved.is_dir():
        return _error(_MSG_NOT_A_DIRECTORY, path=resolved)

    entries = sorted(resolved.iterdir(), key=lambda p: p.name)
    if not entries:
        return ToolResult(ok=True, output=_MSG_DIR_EMPTY.format(path=resolved))
    listing = "\n".join(
        f"{entry.name}/" if entry.is_dir() else entry.name for entry in entries
    )
    return ToolResult(ok=True, output=_cap_stream(listing))


def _cap_stream(text: str) -> str:
    if len(text) <= OUTPUT_CAP:
        return text
    return text[:OUTPUT_CAP] + _TRUNCATION_MARKER.format(cap=OUTPUT_CAP)


def _run_command(
    arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    command, check = _require_string("run_command", arguments, "command")
    if not check.ok:
        return check
    if not permissions.command_permitted(command):
        return _error(
            _MSG_COMMAND_DENIED,
            command=command,
            patterns=_patterns_text(permissions),
        )
    try:
        completed = subprocess.run(
            command,
            shell=True,  # spec-settled; patterns + container are the guardrails
            capture_output=True,
            text=True,
            timeout=permissions.timeout,
        )
    except subprocess.TimeoutExpired:
        return _error(
            _MSG_COMMAND_TIMEOUT,
            command=command,
            timeout=permissions.timeout,
        )
    # Fixed result block (recorded in the E1.3 Delivery Notice); non-zero
    # exit is information for the model, not a tool failure.
    output = (
        f"exit_code: {completed.returncode}\n"
        f"stdout:\n{_cap_stream(completed.stdout)}\n"
        f"stderr:\n{_cap_stream(completed.stderr)}"
    )
    return ToolResult(ok=True, output=output)


def _git(
    arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    args, check = _require_string("git", arguments, "args")
    if not check.ok:
        return check

    try:
        tokens = shlex.split(args)
    except ValueError as exc:
        return _error(_MSG_GIT_PARSE_ERROR, detail=exc)
    if not tokens:
        return _error(_MSG_GIT_NO_SUBCOMMAND)

    subcommand = tokens[0]
    if not permissions.subcommand_permitted(subcommand):
        return _error(
            _MSG_GIT_SUBCOMMAND_DENIED,
            subcommand=subcommand,
            subcommands=_subcommands_text(permissions),
        )

    try:
        completed = subprocess.run(
            ["git", *tokens],
            shell=False,  # spec-settled — never a shell for git
            capture_output=True,
            text=True,
            timeout=permissions.timeout,
        )
    except subprocess.TimeoutExpired:
        return _error(_MSG_GIT_TIMEOUT, args=args, timeout=permissions.timeout)
    # Fixed result block, identical shape to run_command's; non-zero exit is
    # information for the model, not a tool failure.
    output = (
        f"exit_code: {completed.returncode}\n"
        f"stdout:\n{_cap_stream(completed.stdout)}\n"
        f"stderr:\n{_cap_stream(completed.stderr)}"
    )
    return ToolResult(ok=True, output=output)


_HANDLERS = {
    "read_file": _read_file,
    "write_file": _write_file,
    "edit_file": _edit_file,
    "list_dir": _list_dir,
    "run_command": _run_command,
    "git": _git,
}


def execute_tool(
    name: str, arguments: Dict[str, Any], permissions: ToolPermissions
) -> ToolResult:
    """Execute one tool call. Never raises: every expected failure and any
    unexpected handler exception becomes a deterministic, model-facing error
    ``ToolResult`` (§5's handler-exception → tool_error conversion lives
    here, not in the loop)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return _error(
            _MSG_UNKNOWN_TOOL,
            name=name,
            available=", ".join(_TOOL_ORDER),
        )
    try:
        return handler(arguments, permissions)
    except Exception as exc:  # noqa: BLE001 — never-raising surface (§5)
        return _error(
            _MSG_UNEXPECTED,
            tool=name,
            kind=type(exc).__name__,
            detail=exc,
        )
