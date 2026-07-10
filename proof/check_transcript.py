#!/usr/bin/env python3
"""Mechanical cleanliness check for a §9 proof transcript (stdlib only).

Validates a ``--transcript`` JSON against the milestone's acceptance wording
(P1-M1 acceptance item 6 / E1.5 spec §3):

- the §3 Result shape: exactly the seven keys ``status``, ``final_answer``,
  ``transcript``, ``iterations``, ``tokens``, ``model``, ``duration_ms``
- ``status == "completed"`` and a non-empty ``final_answer``
- every step well-formed: ``tool_call`` with a non-empty string ``name`` and
  an object ``args``; non-empty string ``tool_result``; real §3 cost data
  (``ms`` a non-negative integer, ``eval_count`` a positive integer);
  ``iterations`` equal to the step count; total ``tokens`` covering at least
  the per-step ``eval_count`` sum
- no unrepaired error in the final iteration: the last step, if any, is not
  an error result (rule below)
- the proof is genuine (§9's three steps actually happened): a non-error
  ``read_file`` step, then a successful ``edit_file`` step after it, then a
  ``run_command`` step reporting ``exit_code: 0`` after the edit
- with ``--workspace DIR``, belt and braces beyond the model's own test run:
  the workspace file contains the edited line (and no longer the original),
  and the workspace test passes when re-run directly

Error-detection rule (settled by this Epic; recorded in the E1.5 Delivery
Notice): a step's ``tool_result`` is an *error result* iff it starts with one
of the deterministic error forms the engine feeds back —

- ``unknown tool '`` — E1.2 repair feedback and E1.3's unknown-tool result
- ``invalid arguments for tool '`` — E1.2 argument-coercion repair feedback
- ``read_file: `` or ``run_command: `` — every E1.3 error template for these
  tools carries the ``{tool}: `` prefix, and no successful result does
  (``read_file`` success is raw file content; ``run_command`` success starts
  with ``exit_code: ``)
- ``edit_file: ``, except the single success form ``edit_file: replaced ``

A ``run_command`` result with a non-zero exit code is NOT an error result:
per CONTRACT.md §4 a failing test is information for the model, not a tool
failure — it may appear anywhere except as an unverified final state, which
the genuineness and workspace checks close off.

Exit codes: 0 clean · 1 problems found (one ``FAIL:`` line each) ·
2 unreadable/unparseable transcript file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RESULT_KEYS = {
    "status",
    "final_answer",
    "transcript",
    "iterations",
    "tokens",
    "model",
    "duration_ms",
}
STEP_KEYS = {"tool_call", "tool_result", "ms", "eval_count"}

# The proof fixture's edit (proof/workspace-template/app.py) and its test.
ORIGINAL_LINE = "VALUE = 41"
EDITED_LINE = "VALUE = 42"
WORKSPACE_FILE = "app.py"
WORKSPACE_TEST = ["python3", "test_app.py"]
WORKSPACE_TEST_TIMEOUT = 60

EDIT_SUCCESS_PREFIX = "edit_file: replaced "
_ERROR_PREFIXES = (
    "unknown tool '",
    "invalid arguments for tool '",
    "read_file: ",
    "edit_file: ",
    "run_command: ",
)


def is_error_result(tool_result: str) -> bool:
    """The Epic's error-detection rule (see module docstring)."""
    if tool_result.startswith(EDIT_SUCCESS_PREFIX):
        return False
    return tool_result.startswith(_ERROR_PREFIXES)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _step_name(step: object) -> str:
    if isinstance(step, dict) and isinstance(step.get("tool_call"), dict):
        name = step["tool_call"].get("name")
        if isinstance(name, str):
            return name
    return ""


def _step_result(step: object) -> str:
    if isinstance(step, dict) and isinstance(step.get("tool_result"), str):
        return step["tool_result"]
    return ""


def _reports_exit_zero(tool_result: str) -> bool:
    lines = tool_result.splitlines()
    return bool(lines) and lines[0] == "exit_code: 0"


def _check_step(index: int, step: object) -> "list[str]":
    prefix = f"step {index}"
    if not isinstance(step, dict):
        return [f"{prefix}: expected an object, got {type(step).__name__}"]
    problems = []
    missing = sorted(STEP_KEYS - step.keys())
    extra = sorted(step.keys() - STEP_KEYS)
    if missing:
        problems.append(f"{prefix}: missing key(s): {', '.join(missing)}")
    if extra:
        problems.append(f"{prefix}: unexpected key(s): {', '.join(extra)}")

    tool_call = step.get("tool_call")
    if not isinstance(tool_call, dict):
        problems.append(f"{prefix}: tool_call must be an object")
    else:
        name = tool_call.get("name")
        if not (isinstance(name, str) and name):
            problems.append(
                f"{prefix}: tool_call.name must be a non-empty string"
            )
        if not isinstance(tool_call.get("args"), dict):
            problems.append(f"{prefix}: tool_call.args must be an object")

    tool_result = step.get("tool_result")
    if not (isinstance(tool_result, str) and tool_result):
        problems.append(f"{prefix}: tool_result must be a non-empty string")

    if "ms" in step and not (_is_int(step["ms"]) and step["ms"] >= 0):
        problems.append(f"{prefix}: ms must be a non-negative integer")
    if "eval_count" in step and not (
        _is_int(step["eval_count"]) and step["eval_count"] > 0
    ):
        problems.append(
            f"{prefix}: eval_count must be a positive integer (real §3 data)"
        )
    return problems


def check_transcript(data: object) -> "list[str]":
    """Return every cleanliness problem found (empty list == clean)."""
    if not isinstance(data, dict):
        return ["transcript root: expected a JSON object"]
    problems = []
    missing = sorted(RESULT_KEYS - data.keys())
    extra = sorted(data.keys() - RESULT_KEYS)
    if extra:
        problems.append(f"§3 shape: unexpected key(s): {', '.join(extra)}")
    if missing:
        problems.append(f"§3 shape: missing key(s): {', '.join(missing)}")
        return problems  # field checks below would only cascade

    if data["status"] != "completed":
        problems.append(f'status: expected "completed", got {data["status"]!r}')
    final_answer = data["final_answer"]
    if not (isinstance(final_answer, str) and final_answer.strip()):
        problems.append("final_answer: must be a non-empty string")
    if not (isinstance(data["model"], str) and data["model"]):
        problems.append("model: must be a non-empty string")
    if not (_is_int(data["duration_ms"]) and data["duration_ms"] > 0):
        problems.append("duration_ms: must be a positive integer")

    steps = data["transcript"]
    if not isinstance(steps, list):
        problems.append("transcript: must be a list of steps")
        return problems
    for index, step in enumerate(steps, 1):
        problems.extend(_check_step(index, step))

    if not (_is_int(data["iterations"]) and data["iterations"] == len(steps)):
        problems.append(
            f"iterations: must equal the step count "
            f"({data['iterations']!r} != {len(steps)})"
        )
    eval_sum = sum(
        step["eval_count"]
        for step in steps
        if isinstance(step, dict) and _is_int(step.get("eval_count"))
    )
    if not (_is_int(data["tokens"]) and data["tokens"] > 0):
        problems.append("tokens: must be a positive integer (real §3 data)")
    elif data["tokens"] < eval_sum:
        problems.append(
            f"tokens: total ({data['tokens']}) is less than the per-step "
            f"eval_count sum ({eval_sum})"
        )

    # No unrepaired error in the final iteration.
    if steps and is_error_result(_step_result(steps[-1])):
        problems.append(
            "final iteration: last step is an unrepaired error result: "
            + _step_result(steps[-1]).splitlines()[0]
        )

    # Genuineness: §9's read → edit → passing test, in that order.
    read_index = next(
        (
            i
            for i, step in enumerate(steps)
            if _step_name(step) == "read_file"
            and _step_result(step)
            and not is_error_result(_step_result(step))
        ),
        None,
    )
    edit_index = next(
        (
            i
            for i, step in enumerate(steps)
            if _step_name(step) == "edit_file"
            and _step_result(step).startswith(EDIT_SUCCESS_PREFIX)
        ),
        None,
    )
    if read_index is None:
        problems.append("genuineness: no successful read_file step")
    if edit_index is None:
        problems.append("genuineness: no successful edit_file step")
    else:
        if read_index is not None and read_index > edit_index:
            problems.append(
                "genuineness: the successful edit precedes every "
                "successful read_file step"
            )
        test_after_edit = any(
            _step_name(step) == "run_command"
            and _reports_exit_zero(_step_result(step))
            for step in steps[edit_index + 1 :]
        )
        if not test_after_edit:
            problems.append(
                "genuineness: no run_command step reporting exit_code: 0 "
                "after the successful edit"
            )
    return problems


def check_workspace(workspace: Path) -> "list[str]":
    """Belt and braces: assert the edit landed in the workspace and the
    fixture test passes when re-run directly."""
    app = workspace / WORKSPACE_FILE
    if not app.is_file():
        return [f"workspace: '{app}' does not exist"]
    problems = []
    content = app.read_text()
    if EDITED_LINE not in content:
        problems.append(
            f"workspace: {WORKSPACE_FILE} does not contain the edited "
            f"line {EDITED_LINE!r}"
        )
    if ORIGINAL_LINE in content:
        problems.append(
            f"workspace: {WORKSPACE_FILE} still contains the original "
            f"line {ORIGINAL_LINE!r}"
        )
    try:
        completed = subprocess.run(
            WORKSPACE_TEST,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=WORKSPACE_TEST_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return problems + [
            f"workspace: could not re-run {' '.join(WORKSPACE_TEST)!r}: {exc}"
        ]
    if completed.returncode != 0:
        problems.append(
            f"workspace: re-running {' '.join(WORKSPACE_TEST)!r} exited "
            f"{completed.returncode}: "
            + " ".join((completed.stdout + completed.stderr).split())
        )
    return problems


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mechanically check a §9 proof transcript for cleanliness "
            "(and, with --workspace, the workspace state)."
        )
    )
    parser.add_argument("transcript", help="path to the --transcript JSON")
    parser.add_argument(
        "--workspace",
        help=(
            "also assert the run workspace contains the edit and its test "
            "passes when re-run directly"
        ),
    )
    args = parser.parse_args(argv)

    try:
        data = json.loads(Path(args.transcript).read_text())
    except (OSError, ValueError) as exc:
        print(f"check_transcript: cannot read transcript: {exc}", file=sys.stderr)
        return 2

    problems = check_transcript(data)
    if args.workspace:
        problems.extend(check_workspace(Path(args.workspace)))

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(
        f"OK: clean transcript — {data['iterations']} iterations, "
        f"{data['tokens']} tokens, {data['duration_ms']} ms"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
