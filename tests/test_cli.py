"""Offline tests for the §2 CLI (``local_agent_runner/cli.py``).

The scripted fake client is injected via ``main(argv, client=...)``; the
one real-client test targets an unreachable localhost port (connection
refused locally — still no network, no Ollama).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from local_agent_runner.cli import (
    EXIT_COMPLETED,
    EXIT_CONFIG_ERROR,
    EXIT_DID_NOT_CONVERGE,
    EXIT_RUNTIME_ERROR,
    main,
)
from local_agent_runner.ollama_client import ChatMessage, ChatResponse

REPO_ROOT = Path(__file__).parents[1]

RESULT_KEYS = [
    "status",
    "final_answer",
    "transcript",
    "iterations",
    "tokens",
    "model",
    "duration_ms",
]
STEP_KEYS = ["tool_call", "tool_result", "ms", "eval_count"]

# A port from the reserved discard range: nothing listens there, so the
# real client gets connection-refused instantly — offline by construction.
UNREACHABLE_ENDPOINT = "http://127.0.0.1:9"


def response_from(message, eval_count):
    return ChatResponse(
        message=ChatMessage.from_dict(message),
        eval_count=eval_count,
        prompt_eval_count=None,
        raw={"message": message, "eval_count": eval_count},
    )


def native_call_response(name, arguments, eval_count=20):
    return response_from(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        },
        eval_count,
    )


def final_answer_response(text="All done.", eval_count=12):
    return response_from({"role": "assistant", "content": text}, eval_count)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def chat(self, model, messages, tools=None, options=None):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class EndlessToolCaller:
    def __init__(self, path):
        self.path = path
        self.calls = 0

    def chat(self, model, messages, tools=None, options=None):
        self.calls += 1
        return native_call_response("read_file", {"path": str(self.path)})


@pytest.fixture
def workspace(tmp_path):
    """task file, tools.json, a readable target file, a transcript path."""
    target = tmp_path / "app.py"
    target.write_text("line1\nline2\n")
    task = tmp_path / "task.md"
    task.write_text("Read the file and summarize it.")
    tools = tmp_path / "tools.json"
    tools.write_text(
        json.dumps(
            {"enabled": ["read_file"], "allow_paths": [f"{tmp_path}/*"]}
        )
    )
    transcript = tmp_path / "out.json"
    return {
        "tmp_path": tmp_path,
        "target": target,
        "task": task,
        "tools": tools,
        "transcript": transcript,
    }


def base_argv(ws, **overrides):
    argv = [
        "--task", str(ws["task"]),
        "--tools", str(ws["tools"]),
        "--transcript", str(ws["transcript"]),
    ]
    for flag, value in overrides.items():
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    return argv


def assert_one_stderr_line(capsys_result):
    assert capsys_result.out == ""  # script-consumable without parsing stdout
    err = capsys_result.err
    assert err.startswith("local-agent-runner: ")
    assert err.endswith("\n") and err.count("\n") == 1
    return err


# ---------------------------------------------------------------------------
# Exit 0 — completed
# ---------------------------------------------------------------------------


class TestCompleted:
    def test_final_answer_on_stdout_and_valid_transcript(self, workspace, capsys):
        fake = FakeClient(
            [
                native_call_response(
                    "read_file", {"path": str(workspace["target"])}, eval_count=28
                ),
                final_answer_response("Two lines of text.", eval_count=12),
            ]
        )

        rc = main(base_argv(workspace), client=fake)

        assert rc == EXIT_COMPLETED
        captured = capsys.readouterr()
        assert captured.out == "Two lines of text.\n"
        assert captured.err == ""

        data = json.loads(workspace["transcript"].read_text())
        assert list(data.keys()) == RESULT_KEYS  # §3 shape, all seven keys
        assert data["status"] == "completed"
        assert data["final_answer"] == "Two lines of text."
        assert data["iterations"] == 1
        assert data["tokens"] == 40  # sum of the fake's eval_counts
        for step in data["transcript"]:
            assert list(step.keys()) == STEP_KEYS

    def test_task_text_and_default_model(self, workspace, capsys):
        fake = FakeClient([final_answer_response("hi")])
        argv = [
            "--task-text", "say hi",
            "--tools", str(workspace["tools"]),
            "--transcript", str(workspace["transcript"]),
        ]

        rc = main(argv, client=fake)

        assert rc == EXIT_COMPLETED
        assert capsys.readouterr().out == "hi\n"
        data = json.loads(workspace["transcript"].read_text())
        assert data["model"] == "qwen2.5-coder:14b"  # §2 default

    def test_transcript_flag_is_optional(self, workspace, capsys):
        fake = FakeClient([final_answer_response("ok")])
        argv = ["--task-text", "t", "--tools", str(workspace["tools"])]

        assert main(argv, client=fake) == EXIT_COMPLETED
        assert capsys.readouterr().out == "ok\n"


# ---------------------------------------------------------------------------
# Exit 2 — did not converge
# ---------------------------------------------------------------------------


class TestDidNotConverge:
    def test_ceiling_exit_2_transcript_written(self, workspace, capsys):
        client = EndlessToolCaller(workspace["target"])

        rc = main(base_argv(workspace, max_iterations=3), client=client)

        assert rc == EXIT_DID_NOT_CONVERGE
        err = assert_one_stderr_line(capsys.readouterr())
        assert "did not converge" in err

        data = json.loads(workspace["transcript"].read_text())
        assert data["status"] == "max_iterations_exceeded"
        # --max-iterations reached the loop, observable via the fake
        assert client.calls == 3
        assert len(data["transcript"]) == 3


# ---------------------------------------------------------------------------
# Exit 3 — config/tool errors (one-line stderr each; loop never reached)
# ---------------------------------------------------------------------------


class TestConfigErrors:
    def untouched_client(self):
        # empty script: any chat() call would raise IndexError and flip
        # the exit code to 4 — so exit 3 also proves the loop never ran
        return FakeClient([])

    def test_missing_task_and_task_text(self, workspace, capsys):
        rc = main(["--tools", str(workspace["tools"])], client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        assert_one_stderr_line(capsys.readouterr())

    def test_task_and_task_text_are_mutually_exclusive(self, workspace, capsys):
        argv = base_argv(workspace) + ["--task-text", "also"]
        rc = main(argv, client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        assert_one_stderr_line(capsys.readouterr())

    def test_missing_tools_flag(self, workspace, capsys):
        rc = main(["--task-text", "t"], client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        assert_one_stderr_line(capsys.readouterr())

    def test_unreadable_task_file(self, workspace, capsys):
        argv = base_argv(workspace)
        argv[argv.index("--task") + 1] = str(workspace["tmp_path"] / "missing.md")
        rc = main(argv, client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        err = assert_one_stderr_line(capsys.readouterr())
        assert "task file" in err

    def test_invalid_tools_json(self, workspace, capsys):
        workspace["tools"].write_text("{not json")
        rc = main(base_argv(workspace), client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        err = assert_one_stderr_line(capsys.readouterr())
        assert "tools file" in err

    def test_tools_json_not_an_object(self, workspace, capsys):
        workspace["tools"].write_text('["read_file"]')
        rc = main(base_argv(workspace), client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        assert_one_stderr_line(capsys.readouterr())

    def test_unknown_enabled_tool(self, workspace, capsys):
        workspace["tools"].write_text(
            json.dumps({"enabled": ["read_file", "frobnicate"]})
        )
        rc = main(base_argv(workspace), client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        err = assert_one_stderr_line(capsys.readouterr())
        assert "frobnicate" in err

    def test_unwritable_transcript_path(self, workspace, capsys):
        argv = base_argv(
            workspace,
            transcript=workspace["tmp_path"] / "no" / "such" / "dir" / "out.json",
        )
        rc = main(argv, client=self.untouched_client())
        assert rc == EXIT_CONFIG_ERROR
        err = assert_one_stderr_line(capsys.readouterr())
        assert "transcript" in err

    def test_non_integer_max_iterations(self, workspace, capsys):
        rc = main(
            base_argv(workspace, max_iterations="lots"),
            client=self.untouched_client(),
        )
        assert rc == EXIT_CONFIG_ERROR
        assert_one_stderr_line(capsys.readouterr())


# ---------------------------------------------------------------------------
# Exit 4 — runtime errors (transcript with status "error" still written)
# ---------------------------------------------------------------------------


class TestRuntimeErrors:
    def test_connection_error_injected_client(self, workspace, capsys):
        from local_agent_runner.ollama_client import OllamaConnectionError

        fake = FakeClient([OllamaConnectionError("cannot reach Ollama at X")])

        rc = main(base_argv(workspace), client=fake)

        assert rc == EXIT_RUNTIME_ERROR
        err = assert_one_stderr_line(capsys.readouterr())
        assert "cannot reach" in err

        data = json.loads(workspace["transcript"].read_text())
        assert data["status"] == "error"  # failed runs are inspectable
        assert list(data.keys()) == RESULT_KEYS
        assert data["final_answer"] is None

    def test_unreachable_endpoint_with_real_client(self, workspace, capsys):
        # no injection: --endpoint must reach the real OllamaClient
        rc = main(base_argv(workspace, endpoint=UNREACHABLE_ENDPOINT))

        assert rc == EXIT_RUNTIME_ERROR
        err = assert_one_stderr_line(capsys.readouterr())
        assert "127.0.0.1:9" in err
        data = json.loads(workspace["transcript"].read_text())
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Both §2 entry points invoke the CLI
# ---------------------------------------------------------------------------


class TestEntryPoints:
    def entry_point_check(self, command):
        completed = subprocess.run(
            command + ["--task-text", "t"],  # missing --tools → config error
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert completed.returncode == EXIT_CONFIG_ERROR
        assert completed.stdout == ""
        assert completed.stderr.startswith("local-agent-runner: ")
        assert completed.stderr.count("\n") == 1

    def test_python_dash_m(self):
        self.entry_point_check([sys.executable, "-m", "local_agent_runner"])

    def test_console_script(self):
        script = shutil.which("local-agent-runner")
        if script is None:
            pytest.skip(
                "console script not on PATH (install with pip install -e '.[dev]')"
            )
        self.entry_point_check([script])
