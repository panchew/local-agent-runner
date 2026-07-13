"""The §2 CLI: file-based I/O, exit codes 0/2/3/4 (CONTRACT.md §2).

stdout is the final answer only; the transcript goes to ``--transcript``
(§2's file-based I/O discipline). Every non-zero exit prints exactly one
reason line to stderr, prefixed ``local-agent-runner:``, so callers can
script on exit code + stderr without parsing stdout.

Config-time strictness (exit 3) is distinct from the model's runtime
repair: a name in ``enabled`` that is not a known tool is the *caller's*
mistake and fails at startup; an unknown tool the *model* calls mid-run is
§5 repair feedback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from local_agent_runner.loop import (
    DEFAULT_MAX_ITERATIONS,
    STATUS_COMPLETED,
    STATUS_MAX_ITERATIONS_EXCEEDED,
    Result,
    run,
)
from local_agent_runner.ollama_client import DEFAULT_ENDPOINT
from local_agent_runner.tools import ToolPermissions, tool_definitions

DEFAULT_MODEL = "qwen2.5-coder:14b"

EXIT_COMPLETED = 0
EXIT_DID_NOT_CONVERGE = 2
EXIT_CONFIG_ERROR = 3
EXIT_RUNTIME_ERROR = 4


class ConfigError(Exception):
    """A caller mistake detected before the loop starts (exit 3)."""


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on bad flags; §2 reserves 2 for did-not-converge,
    so flag errors are rerouted to the exit-3 path instead."""

    def error(self, message: str) -> "None":  # type: ignore[override]
        raise ConfigError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="local-agent-runner",
        description=(
            "Run a tool-calling loop with a local Ollama model: one task, "
            "one loop, one result (CONTRACT.md §2)."
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"ollama model tag (default: {DEFAULT_MODEL})",
    )
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument(
        "--task",
        help="path to a file whose content is the task instruction",
    )
    task_group.add_argument(
        "--task-text",
        help="the task instruction given directly",
    )
    parser.add_argument(
        "--tools",
        required=True,
        help="path to a tools.json: enabled tools + permissions (§4)",
    )
    parser.add_argument(
        "--context",
        help="path to a file of optional scoped reference material (§3 context)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"loop ceiling (default {DEFAULT_MAX_ITERATIONS})",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"ollama HTTP API endpoint (default {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--transcript",
        help="path to write the full run record (§3 Result JSON)",
    )
    return parser


def _load_task(args: argparse.Namespace) -> str:
    if args.task_text is not None:
        return args.task_text
    try:
        return Path(args.task).read_text()
    except OSError as exc:
        raise ConfigError(f"cannot read task file '{args.task}': {exc}")


def _load_context(args: argparse.Namespace) -> Optional[str]:
    if args.context is None:
        return None
    try:
        return Path(args.context).read_text()
    except OSError as exc:
        raise ConfigError(f"cannot read context file '{args.context}': {exc}")


def _load_permissions(tools_path: str) -> ToolPermissions:
    try:
        text = Path(tools_path).read_text()
    except OSError as exc:
        raise ConfigError(f"cannot read tools file '{tools_path}': {exc}")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"invalid JSON in tools file '{tools_path}': {exc}")
    if not isinstance(data, dict):
        raise ConfigError(
            f"tools file '{tools_path}' must contain a JSON object (§4 shape)"
        )
    permissions = ToolPermissions.from_dict(data)
    known = {
        definition["function"]["name"]
        for definition in tool_definitions(permissions)
    }
    unknown = [name for name in permissions.enabled if name not in known]
    if unknown:
        raise ConfigError(
            "unknown tool(s) in 'enabled': "
            + ", ".join(repr(name) for name in unknown)
        )
    return permissions


def _check_transcript_path(transcript: Optional[str]) -> Optional[Path]:
    if transcript is None:
        return None
    path = Path(transcript)
    if path.is_dir():
        raise ConfigError(f"transcript path '{transcript}' is a directory")
    parent = path.parent if str(path.parent) else Path(".")
    if not parent.is_dir():
        raise ConfigError(
            f"transcript path '{transcript}' is not writable: "
            f"directory '{parent}' does not exist"
        )
    if not os.access(parent, os.W_OK):
        raise ConfigError(
            f"transcript path '{transcript}' is not writable: "
            f"directory '{parent}' is not writable"
        )
    return path


def _write_transcript(path: Optional[Path], result: Result) -> None:
    """Best effort: written for every run that reached the loop, including
    ``error`` and ``max_iterations_exceeded`` runs — failed runs must be
    inspectable (§6)."""
    if path is None:
        return
    try:
        path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
    except OSError as exc:
        _stderr(f"could not write transcript to '{path}': {exc}")


def _stderr(reason: str) -> None:
    # One line, always: collapse any embedded newlines/whitespace runs.
    print("local-agent-runner: " + " ".join(str(reason).split()), file=sys.stderr)


def main(
    argv: Optional[List[str]] = None, client: Optional[Any] = None
) -> int:
    """CLI entry point; returns the §2 exit code. ``client`` is injectable
    for offline tests (passed through to ``run``)."""
    try:
        args = build_parser().parse_args(argv)
        task = _load_task(args)
        context = _load_context(args)
        permissions = _load_permissions(args.tools)
        transcript_path = _check_transcript_path(args.transcript)
    except ConfigError as exc:
        _stderr(str(exc))
        return EXIT_CONFIG_ERROR

    try:
        result = run(
            args.model,
            task,
            permissions,
            endpoint=args.endpoint,
            max_iterations=args.max_iterations,
            context=context,
            client=client,
        )
    except Exception as exc:  # loop absorbs OllamaClientError; this is the
        # anything-else net — §2 maps unexpected failure to exit 4
        _stderr(f"unexpected error: {type(exc).__name__}: {exc}")
        return EXIT_RUNTIME_ERROR

    _write_transcript(transcript_path, result)

    if result.status == STATUS_COMPLETED:
        print(result.final_answer)
        return EXIT_COMPLETED
    if result.status == STATUS_MAX_ITERATIONS_EXCEEDED:
        _stderr(
            f"did not converge within {args.max_iterations} iterations"
        )
        return EXIT_DID_NOT_CONVERGE
    _stderr(result.error or "runtime error")
    return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
