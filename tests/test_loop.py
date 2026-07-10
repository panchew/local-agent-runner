"""Offline tests for the §5 execution loop (``local_agent_runner/loop.py``).

No GPU, no Ollama server, no network: a scripted fake client returns a
programmed sequence of ``ChatResponse``s (built from the recorded fixtures
where they fit) via ``run(client=...)``.
"""

import json
from pathlib import Path

import pytest

from local_agent_runner.loop import (
    DEFAULT_MAX_ITERATIONS,
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_MAX_ITERATIONS_EXCEEDED,
    run,
)
from local_agent_runner.ollama_client import (
    ChatMessage,
    ChatResponse,
    OllamaConnectionError,
)
from local_agent_runner.tools import ToolPermissions, tool_definitions

FIXTURES_DIR = Path(__file__).parent / "fixtures"

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


# ---------------------------------------------------------------------------
# Scripted fake client + fixture-shaped response builders
# ---------------------------------------------------------------------------


def load_fixture(name):
    return json.loads((FIXTURES_DIR / name).read_text())


def response_from(data):
    """Build a ChatResponse exactly as OllamaClient.chat does from a
    recorded (or fixture-shaped) response dict."""
    return ChatResponse(
        message=ChatMessage.from_dict(data.get("message") or {}),
        eval_count=data.get("eval_count"),
        prompt_eval_count=data.get("prompt_eval_count"),
        raw=data,
    )


def fixture_response(name):
    return response_from(load_fixture(name))


def native_call_response(name, arguments, eval_count=20):
    """A native-mode tool call (fixture-shaped: llama3.1 delivery, §1.2)."""
    return response_from(
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": name, "arguments": arguments}}
                ],
            },
            "eval_count": eval_count,
        }
    )


def content_call_response(name, arguments, eval_count=30):
    """A content-mode tool call (fixture-shaped: qwen2.5-coder delivery,
    §1.2 — fenced JSON with surrounding prose, native field empty)."""
    call = json.dumps({"name": name, "arguments": arguments})
    return response_from(
        {
            "message": {
                "role": "assistant",
                "content": f"I'll call the tool now.\n\n```json\n{call}\n```\n",
                "tool_calls": [],
            },
            "eval_count": eval_count,
        }
    )


def final_answer_response(text="All done.", eval_count=12):
    return response_from(
        {
            "message": {"role": "assistant", "content": text},
            "eval_count": eval_count,
        }
    )


class FakeClient:
    """Returns the scripted items in order; an Exception item is raised.
    Records every chat() call for observability."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, model, messages, tools=None, options=None):
        self.calls.append(
            {
                "model": model,
                "messages": [
                    m.to_dict() if isinstance(m, ChatMessage) else m
                    for m in messages
                ],
                "tools": tools,
                "options": options,
            }
        )
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class EndlessToolCaller:
    """Never stops calling tools — the ceiling must halt the loop."""

    def __init__(self, path):
        self.path = path
        self.calls = 0

    def chat(self, model, messages, tools=None, options=None):
        self.calls += 1
        return native_call_response("read_file", {"path": str(self.path)}, eval_count=5)


@pytest.fixture
def workspace(tmp_path):
    """A permitted file plus permissions scoped to tmp_path."""
    file = tmp_path / "app.py"
    file.write_text("line1\nline2\nline3\n")
    permissions = ToolPermissions.from_dict(
        {
            "enabled": ["read_file", "edit_file", "run_command"],
            "allow_paths": [f"{tmp_path}/*"],
            "allow_commands": ["echo *"],
        }
    )
    return file, permissions


# ---------------------------------------------------------------------------
# Termination: final answer / ceiling / client error
# ---------------------------------------------------------------------------


class TestTermination:
    def test_immediate_final_answer(self, workspace):
        _, permissions = workspace
        fake = FakeClient([fixture_response("chat_final_answer.json")])

        result = run("qwen2.5-coder:14b", "do the thing", permissions, client=fake)

        assert result.status == STATUS_COMPLETED
        assert result.final_answer == "The edit is complete and the test passes."
        assert result.transcript == []
        assert result.iterations == 0
        assert result.tokens == 12  # the final turn's eval_count is counted (§6)
        assert result.model == "qwen2.5-coder:14b"
        assert result.duration_ms >= 0

    def test_ceiling_halts_endless_tool_caller(self, workspace):
        file, permissions = workspace
        client = EndlessToolCaller(file)

        result = run("m", "task", permissions, max_iterations=4, client=client)

        assert result.status == STATUS_MAX_ITERATIONS_EXCEEDED
        assert client.calls == 4  # exactly max_iterations turns
        assert len(result.transcript) == 4
        assert result.iterations == 4
        assert result.final_answer is None
        assert result.tokens == 20

    def test_default_ceiling_is_ten(self, workspace):
        file, permissions = workspace
        client = EndlessToolCaller(file)

        result = run("m", "task", permissions, client=client)

        assert result.status == STATUS_MAX_ITERATIONS_EXCEEDED
        assert client.calls == DEFAULT_MAX_ITERATIONS == 10

    def test_client_error_mid_run_preserves_transcript(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": str(file)}, eval_count=28),
                OllamaConnectionError("cannot reach Ollama at http://localhost:11434"),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        assert result.status == STATUS_ERROR
        assert "cannot reach Ollama" in result.error
        assert len(result.transcript) == 1  # prior steps preserved
        assert result.transcript[0]["tool_result"] == "line1\nline2\nline3\n"
        assert result.final_answer is None
        assert result.tokens == 28  # only turns that produced a response


# ---------------------------------------------------------------------------
# Tool rounds: both delivery modes, history fidelity, transcript shape
# ---------------------------------------------------------------------------


class TestToolRounds:
    def test_native_tool_call_then_final_answer(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": str(file)}, eval_count=28),
                final_answer_response("The file has three lines.", eval_count=12),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        assert result.status == STATUS_COMPLETED
        assert result.final_answer == "The file has three lines."
        assert result.iterations == 1
        step = result.transcript[0]
        assert step["tool_call"] == {"name": "read_file", "args": {"path": str(file)}}
        assert step["tool_result"] == "line1\nline2\nline3\n"  # ToolResult.output
        assert isinstance(step["ms"], int) and step["ms"] >= 0
        assert step["eval_count"] == 28
        assert result.tokens == 28 + 12  # sum over both turns

    def test_native_assistant_message_appended_as_produced(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": str(file)}),
                final_answer_response(),
            ]
        )

        run("m", "task", permissions, client=fake)

        second_turn = fake.calls[1]["messages"]
        assert second_turn[0] == {"role": "user", "content": "task"}
        assistant = second_turn[1]
        assert assistant["role"] == "assistant"
        assert assistant["tool_calls"] == [
            {"function": {"name": "read_file", "arguments": {"path": str(file)}}}
        ]  # native tool_calls intact
        tool = second_turn[2]
        assert tool == {"role": "tool", "content": "line1\nline2\nline3\n"}

    def test_content_mode_drives_loop_with_coercion(self, workspace):
        file, permissions = workspace
        # qwen-shaped delivery with llama-shaped mistyping: "2"/"3" coerce.
        fake = FakeClient(
            [
                content_call_response(
                    "read_file",
                    {"path": str(file), "start_line": "2", "end_line": "3"},
                    eval_count=52,
                ),
                final_answer_response(eval_count=9),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        assert result.status == STATUS_COMPLETED
        step = result.transcript[0]
        # executed args are post-coercion
        assert step["tool_call"]["args"] == {
            "path": str(file),
            "start_line": 2,
            "end_line": 3,
        }
        assert step["tool_result"] == "line2\nline3\n"
        assert result.tokens == 61
        # the assistant turn is fed back as produced: content JSON as content
        assistant = fake.calls[1]["messages"][1]
        assert assistant["role"] == "assistant"
        assert "```json" in assistant["content"]

    def test_tool_error_result_is_repair_feedback_not_crash(self, workspace):
        file, permissions = workspace
        # missing file: execute_tool returns ok=False; the loop feeds it back
        missing = file.parent / "nope.py"
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": str(missing)}),
                final_answer_response(),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        assert result.status == STATUS_COMPLETED
        assert "does not exist" in result.transcript[0]["tool_result"]


# ---------------------------------------------------------------------------
# The repair paths (§5 / milestone AC quartet + invalid arguments),
# each converging afterwards
# ---------------------------------------------------------------------------


class TestRepairPaths:
    def _assert_converged(self, result, repair_steps):
        assert result.status == STATUS_COMPLETED
        assert result.iterations == repair_steps + 1

    def test_malformed_call_content_mode_then_valid(self, workspace):
        # E1.2 classifies unparseable content as a final answer, so the
        # loop-visible "malformed call" is a parseable call with bad
        # arguments: here a fenced call missing its required argument.
        file, permissions = workspace
        fake = FakeClient(
            [
                content_call_response("read_file", {}, eval_count=40),
                content_call_response("read_file", {"path": str(file)}, eval_count=30),
                final_answer_response(eval_count=10),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        self._assert_converged(result, repair_steps=1)
        step = result.transcript[0]
        assert step["tool_call"] == {"name": "read_file", "args": {}}
        assert "invalid arguments" in step["tool_result"]
        assert "missing required argument" in step["tool_result"]
        assert result.transcript[1]["tool_result"] == "line1\nline2\nline3\n"
        assert result.tokens == 80

    def test_unknown_tool_then_valid(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                fixture_response("chat_native_unknown_tool.json"),
                native_call_response("read_file", {"path": str(file)}),
                final_answer_response(),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        self._assert_converged(result, repair_steps=1)
        step = result.transcript[0]
        assert "unknown tool" in step["tool_result"]
        # the repair step records what the model attempted
        attempted = load_fixture("chat_native_unknown_tool.json")["message"][
            "tool_calls"
        ][0]["function"]
        assert step["tool_call"]["name"] == attempted["name"]
        assert step["tool_call"]["args"] == attempted["arguments"]

    def test_invalid_arguments_then_valid(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                fixture_response("chat_native_uncoercible_argument.json"),
                native_call_response("read_file", {"path": str(file)}),
                final_answer_response(),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        self._assert_converged(result, repair_steps=1)
        assert "invalid arguments" in result.transcript[0]["tool_result"]

    def test_denied_permission_then_valid(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": "/etc/passwd"}),
                native_call_response("read_file", {"path": str(file)}),
                final_answer_response(),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        self._assert_converged(result, repair_steps=1)
        step = result.transcript[0]
        assert "denied" in step["tool_result"]  # ToolResult.ok == False fed back
        assert step["tool_call"]["name"] == "read_file"

    def test_handler_failure_then_valid(self, workspace, tmp_path):
        file, permissions = workspace
        # a genuinely unexpected handler exception: read_text() raises
        # UnicodeDecodeError on invalid UTF-8; execute_tool converts it
        binary = tmp_path / "binary.dat"
        binary.write_bytes(b"\xff\xfe\xff\x00")
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": str(binary)}),
                native_call_response("read_file", {"path": str(file)}),
                final_answer_response(),
            ]
        )

        result = run("m", "task", permissions, client=fake)

        self._assert_converged(result, repair_steps=1)
        assert "unexpected error" in result.transcript[0]["tool_result"]


# ---------------------------------------------------------------------------
# Message seeding, plumbing, and the §3 Result shape
# ---------------------------------------------------------------------------


class TestSeedingAndPlumbing:
    def test_message_seeding_task_only(self, workspace):
        _, permissions = workspace
        fake = FakeClient([final_answer_response()])

        run("m", "the task", permissions, client=fake)

        assert fake.calls[0]["messages"] == [{"role": "user", "content": "the task"}]

    def test_message_seeding_with_system_and_context(self, workspace):
        _, permissions = workspace
        fake = FakeClient([final_answer_response()])

        run("m", "the task", permissions, system="SYS", context="CTX", client=fake)

        assert fake.calls[0]["messages"] == [
            {"role": "system", "content": "SYS"},
            {"role": "system", "content": "CTX"},  # context as a system-role message
            {"role": "user", "content": "the task"},
        ]

    def test_tool_definitions_and_options_reach_the_client(self, workspace):
        _, permissions = workspace
        fake = FakeClient([final_answer_response()])

        run("m", "task", permissions, options={"temperature": 0}, client=fake)

        assert fake.calls[0]["tools"] == tool_definitions(permissions)
        assert fake.calls[0]["options"] == {"temperature": 0}
        assert fake.calls[0]["model"] == "m"

    def test_eval_count_none_counts_as_zero(self, workspace):
        file, permissions = workspace
        call = native_call_response("read_file", {"path": str(file)})
        call.eval_count = None
        fake = FakeClient([call, final_answer_response(eval_count=7)])

        result = run("m", "task", permissions, client=fake)

        assert result.tokens == 7
        assert result.transcript[0]["eval_count"] is None  # absent ≠ measured zero


class TestResultShape:
    def test_to_dict_is_exactly_the_section_3_shape(self, workspace):
        file, permissions = workspace
        fake = FakeClient(
            [
                native_call_response("read_file", {"path": str(file)}, eval_count=28),
                final_answer_response(eval_count=12),
            ]
        )

        result = run("m", "task", permissions, client=fake)
        data = result.to_dict()

        assert list(data.keys()) == RESULT_KEYS
        for step in data["transcript"]:
            assert list(step.keys()) == STEP_KEYS
            assert list(step["tool_call"].keys()) == ["name", "args"]
        # tokens equals the sum of the fake client's eval_counts
        assert data["tokens"] == 40
        json.dumps(data)  # JSON-serializable as-is

    def test_error_result_to_dict_has_no_extra_field(self, workspace):
        _, permissions = workspace
        fake = FakeClient([OllamaConnectionError("boom")])

        result = run("m", "task", permissions, client=fake)
        data = result.to_dict()

        assert list(data.keys()) == RESULT_KEYS  # the reason stays off §3
        assert data["status"] == STATUS_ERROR
        assert data["final_answer"] is None
        assert result.error == "boom"
