"""Offline unit tests for proof/check_transcript.py (E1.5).

The checker is acceptance machinery — these tests pin it against synthetic
pass/fail transcripts (§3 shape, step well-formedness, the error-detection
rule, the no-unrepaired-final-error rule, §9 genuineness) and against real
copies of the proof workspace template. No GPU, no Docker, no network.
"""

import importlib.util
import json
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHECKER_PATH = _REPO_ROOT / "proof" / "check_transcript.py"
_TEMPLATE = _REPO_ROOT / "proof" / "workspace-template"

_spec = importlib.util.spec_from_file_location("check_transcript", _CHECKER_PATH)
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)


# ---------------------------------------------------------------------------
# Builders: a known-clean transcript, mutated per test.
# ---------------------------------------------------------------------------

READ_RESULT = "VALUE = 41\n\n\ndef get_value():\n    return VALUE\n"
EDIT_RESULT = "edit_file: replaced 1 occurrence in '/work/workspace/app.py'."
TEST_PASS_RESULT = "exit_code: 0\nstdout:\nPASS: get_value() == 42\n\nstderr:\n"
TEST_FAIL_RESULT = (
    "exit_code: 1\nstdout:\nFAIL: get_value() == 41, expected 42\n\nstderr:\n"
)

# Verbatim engine error forms (tools.py templates / tool_calls.py repair
# messages) the detection rule must recognize.
ERR_PATH_DENIED = (
    "read_file: access to path '/etc/passwd' is denied. Only paths matching "
    "these allow_paths globs are permitted: /work/workspace/**"
)
ERR_FILE_MISSING = (
    "read_file: file '/work/workspace/nope.py' does not exist. "
    "Provide the path of an existing file."
)
ERR_OLD_NOT_FOUND = (
    "edit_file: 'old' text not found in '/work/workspace/app.py'. "
    "Provide 'old' exactly as it appears in the file, including whitespace."
)
ERR_COMMAND_DENIED = (
    "run_command: command 'pytest' is denied. Only commands matching these "
    "allow_commands patterns are permitted (deny_commands patterns win): "
    "python3 test_app.py"
)
ERR_COMMAND_TIMEOUT = (
    "run_command: command 'python3 test_app.py' timed out after 60 seconds "
    "and was killed. Use a command that finishes within the timeout."
)
ERR_UNKNOWN_TOOL_PARSER = (
    "unknown tool 'write_file'. The enabled tools are: edit_file, read_file, "
    "run_command."
)
ERR_UNKNOWN_TOOL_EXECUTOR = (
    "unknown tool 'write_file'. Available tools: read_file, edit_file, "
    "run_command."
)
ERR_INVALID_ARGUMENTS = (
    "invalid arguments for tool 'read_file': missing required argument(s): "
    "'path'. Provide every required argument listed in the tool's schema."
)


def step(name, result, args=None, ms=1200, eval_count=30):
    return {
        "tool_call": {"name": name, "args": args if args is not None else {}},
        "tool_result": result,
        "ms": ms,
        "eval_count": eval_count,
    }


def read_step():
    return step("read_file", READ_RESULT, {"path": "app.py"})


def edit_step():
    return step(
        "edit_file",
        EDIT_RESULT,
        {"path": "app.py", "old": "VALUE = 41", "new": "VALUE = 42"},
    )


def run_step(result=TEST_PASS_RESULT):
    return step("run_command", result, {"command": "python3 test_app.py"})


def clean_transcript(steps=None):
    steps = (
        steps if steps is not None else [read_step(), edit_step(), run_step()]
    )
    return {
        "status": "completed",
        "final_answer": "Changed VALUE from 41 to 42; the test passes.",
        "transcript": steps,
        "iterations": len(steps),
        "tokens": sum(
            s["eval_count"]
            for s in steps
            if isinstance(s, dict) and isinstance(s.get("eval_count"), int)
        )
        + 25,
        "model": "qwen2.5-coder:14b",
        "duration_ms": 5000,
    }


def problems(data):
    return ct.check_transcript(data)


# ---------------------------------------------------------------------------
# The clean case
# ---------------------------------------------------------------------------


class TestCleanTranscript:
    def test_clean_transcript_has_no_problems(self):
        assert problems(clean_transcript()) == []

    def test_extra_reads_and_rechecks_are_clean(self):
        steps = [
            read_step(),
            run_step(TEST_FAIL_RESULT),  # ran the test early; it fails: fine
            edit_step(),
            read_step(),  # re-read to double-check: fine
            run_step(),
        ]
        assert problems(clean_transcript(steps)) == []

    def test_repair_round_mid_run_is_clean(self):
        # A denied command mid-run is the §5 repair loop working — clean as
        # long as the final iteration is not an error.
        steps = [
            read_step(),
            edit_step(),
            step("run_command", ERR_COMMAND_DENIED, {"command": "pytest"}),
            run_step(),
        ]
        assert problems(clean_transcript(steps)) == []


# ---------------------------------------------------------------------------
# §3 shape
# ---------------------------------------------------------------------------


class TestResultShape:
    def test_non_object_root_fails(self):
        assert problems([1, 2]) == ["transcript root: expected a JSON object"]

    def test_missing_key_fails(self):
        data = clean_transcript()
        del data["tokens"]
        assert any("missing key(s): tokens" in p for p in problems(data))

    def test_unexpected_key_fails(self):
        data = clean_transcript()
        data["error"] = "boom"
        assert any("unexpected key(s): error" in p for p in problems(data))

    def test_status_not_completed_fails(self):
        data = clean_transcript()
        data["status"] = "max_iterations_exceeded"
        assert any(p.startswith("status:") for p in problems(data))

    def test_empty_final_answer_fails(self):
        data = clean_transcript()
        data["final_answer"] = "   "
        assert any(p.startswith("final_answer:") for p in problems(data))

    def test_none_final_answer_fails(self):
        data = clean_transcript()
        data["final_answer"] = None
        assert any(p.startswith("final_answer:") for p in problems(data))

    def test_empty_model_fails(self):
        data = clean_transcript()
        data["model"] = ""
        assert any(p.startswith("model:") for p in problems(data))

    def test_zero_duration_fails(self):
        data = clean_transcript()
        data["duration_ms"] = 0
        assert any(p.startswith("duration_ms:") for p in problems(data))

    def test_iterations_mismatch_fails(self):
        data = clean_transcript()
        data["iterations"] = 7
        assert any(p.startswith("iterations:") for p in problems(data))

    def test_tokens_below_step_sum_fails(self):
        data = clean_transcript()
        data["tokens"] = 10  # three steps of 30 each
        assert any("per-step eval_count sum" in p for p in problems(data))

    def test_non_integer_tokens_fails(self):
        data = clean_transcript()
        data["tokens"] = None
        assert any(p.startswith("tokens:") for p in problems(data))

    def test_transcript_not_a_list_fails(self):
        data = clean_transcript()
        data["transcript"] = {}
        assert any(p.startswith("transcript:") for p in problems(data))


# ---------------------------------------------------------------------------
# Step well-formedness
# ---------------------------------------------------------------------------


class TestStepShape:
    def test_step_not_an_object_fails(self):
        data = clean_transcript([read_step(), edit_step(), run_step(), 42])
        assert any("step 4: expected an object" in p for p in problems(data))

    def test_empty_tool_name_fails(self):
        bad = read_step()
        bad["tool_call"]["name"] = ""
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("tool_call.name" in p for p in problems(data))

    def test_args_not_object_fails(self):
        bad = read_step()
        bad["tool_call"]["args"] = "app.py"
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("tool_call.args" in p for p in problems(data))

    def test_empty_tool_result_fails(self):
        bad = read_step()
        bad["tool_result"] = ""
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("tool_result" in p for p in problems(data))

    def test_missing_step_key_fails(self):
        bad = read_step()
        del bad["ms"]
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("step 1: missing key(s): ms" in p for p in problems(data))

    def test_unexpected_step_key_fails(self):
        bad = read_step()
        bad["note"] = "hi"
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any(
            "step 1: unexpected key(s): note" in p for p in problems(data)
        )

    def test_negative_ms_fails(self):
        bad = read_step()
        bad["ms"] = -1
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("ms must be" in p for p in problems(data))

    def test_boolean_ms_fails(self):
        bad = read_step()
        bad["ms"] = True
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("ms must be" in p for p in problems(data))

    def test_null_eval_count_fails(self):
        # Acceptance demands real per-step §3 cost data on a live run.
        bad = read_step()
        bad["eval_count"] = None
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("eval_count must be" in p for p in problems(data))

    def test_zero_eval_count_fails(self):
        bad = read_step()
        bad["eval_count"] = 0
        data = clean_transcript([bad, edit_step(), run_step()])
        assert any("eval_count must be" in p for p in problems(data))


# ---------------------------------------------------------------------------
# The error-detection rule
# ---------------------------------------------------------------------------


class TestErrorDetectionRule:
    def test_engine_error_forms_are_errors(self):
        for form in (
            ERR_PATH_DENIED,
            ERR_FILE_MISSING,
            ERR_OLD_NOT_FOUND,
            ERR_COMMAND_DENIED,
            ERR_COMMAND_TIMEOUT,
            ERR_UNKNOWN_TOOL_PARSER,
            ERR_UNKNOWN_TOOL_EXECUTOR,
            ERR_INVALID_ARGUMENTS,
        ):
            assert ct.is_error_result(form), form

    def test_success_forms_are_not_errors(self):
        for form in (READ_RESULT, EDIT_RESULT, TEST_PASS_RESULT):
            assert not ct.is_error_result(form), form

    def test_nonzero_exit_code_is_not_an_error(self):
        # CONTRACT.md §4: a failing test is information, not a tool failure.
        assert not ct.is_error_result(TEST_FAIL_RESULT)


# ---------------------------------------------------------------------------
# Final-iteration and genuineness rules
# ---------------------------------------------------------------------------


class TestFinalIterationAndGenuineness:
    def test_error_in_final_iteration_fails(self):
        steps = [
            read_step(),
            edit_step(),
            run_step(),
            step("run_command", ERR_COMMAND_DENIED, {"command": "pytest"}),
        ]
        data = clean_transcript(steps)
        assert any("final iteration" in p for p in problems(data))

    def test_failing_test_in_final_iteration_fails_genuineness(self):
        # exit_code: 1 last is not an "error result", but there is then no
        # passing test after the edit — the genuineness rule catches it.
        steps = [read_step(), edit_step(), run_step(TEST_FAIL_RESULT)]
        data = clean_transcript(steps)
        found = problems(data)
        assert any("exit_code: 0" in p for p in found)

    def test_missing_read_fails(self):
        data = clean_transcript([edit_step(), run_step()])
        assert any("read_file" in p for p in problems(data))

    def test_missing_edit_fails(self):
        data = clean_transcript([read_step(), run_step()])
        assert any(
            "no successful edit_file step" in p for p in problems(data)
        )

    def test_failed_edit_only_fails(self):
        failed_edit = step(
            "edit_file", ERR_OLD_NOT_FOUND, {"path": "app.py"}
        )
        data = clean_transcript([read_step(), failed_edit, run_step()])
        assert any(
            "no successful edit_file step" in p for p in problems(data)
        )

    def test_read_only_after_edit_fails(self):
        data = clean_transcript([edit_step(), read_step(), run_step()])
        assert any("precedes every" in p for p in problems(data))

    def test_passing_test_only_before_edit_fails(self):
        data = clean_transcript([read_step(), run_step(), edit_step()])
        assert any(
            "after the successful edit" in p for p in problems(data)
        )

    def test_empty_transcript_fails_genuineness(self):
        data = clean_transcript([])
        found = problems(data)
        assert any("read_file" in p for p in found)
        assert any("edit_file" in p for p in found)


# ---------------------------------------------------------------------------
# Workspace check (against real copies of the committed template)
# ---------------------------------------------------------------------------


def make_workspace(tmp_path, edited):
    workspace = tmp_path / "workspace"
    shutil.copytree(_TEMPLATE, workspace)
    if edited:
        app = workspace / "app.py"
        app.write_text(app.read_text().replace("VALUE = 41", "VALUE = 42"))
    return workspace


class TestWorkspaceCheck:
    def test_edited_workspace_is_clean(self, tmp_path):
        assert ct.check_workspace(make_workspace(tmp_path, edited=True)) == []

    def test_pristine_workspace_fails(self, tmp_path):
        found = ct.check_workspace(make_workspace(tmp_path, edited=False))
        assert any("edited line" in p for p in found)
        assert any("original line" in p for p in found)
        assert any("exited 1" in p for p in found)

    def test_missing_app_file_fails(self, tmp_path):
        workspace = make_workspace(tmp_path, edited=True)
        (workspace / "app.py").unlink()
        found = ct.check_workspace(workspace)
        assert found and "does not exist" in found[0]


# ---------------------------------------------------------------------------
# CLI surface (exit codes 0/1/2)
# ---------------------------------------------------------------------------


class TestMain:
    def _write(self, tmp_path, data):
        path = tmp_path / "transcript.json"
        path.write_text(json.dumps(data))
        return str(path)

    def test_clean_transcript_exits_0(self, tmp_path, capsys):
        code = ct.main([self._write(tmp_path, clean_transcript())])
        assert code == 0
        assert capsys.readouterr().out.startswith("OK: clean transcript")

    def test_problems_exit_1_and_print_fail_lines(self, tmp_path, capsys):
        data = clean_transcript()
        data["status"] = "error"
        code = ct.main([self._write(tmp_path, data)])
        assert code == 1
        assert "FAIL: status:" in capsys.readouterr().out

    def test_unreadable_file_exits_2(self, tmp_path, capsys):
        code = ct.main([str(tmp_path / "missing.json")])
        assert code == 2
        assert "cannot read transcript" in capsys.readouterr().err

    def test_invalid_json_exits_2(self, tmp_path, capsys):
        path = tmp_path / "bad.json"
        path.write_text("{not json")
        assert ct.main([str(path)]) == 2
        assert "cannot read transcript" in capsys.readouterr().err

    def test_workspace_flag_checks_workspace(self, tmp_path, capsys):
        transcript = self._write(tmp_path, clean_transcript())
        pristine = make_workspace(tmp_path, edited=False)
        code = ct.main([transcript, "--workspace", str(pristine)])
        assert code == 1
        assert "FAIL: workspace:" in capsys.readouterr().out

    def test_workspace_flag_passes_on_edited_workspace(self, tmp_path, capsys):
        transcript = self._write(tmp_path, clean_transcript())
        edited = make_workspace(tmp_path, edited=True)
        assert ct.main([transcript, "--workspace", str(edited)]) == 0
