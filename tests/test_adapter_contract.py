"""Offline proof that CONTRACT.md §7 step 2's exact invocation pattern —
DoD-shaped ``--task``, scoped ``--context``, coding-set ``--tools``, an
explicit ``--model`` tag — converges to a stable, adapter-consumable result
using only exit code and the ``--transcript`` §3 Result JSON (Epic E3.1).

SN-3 (binding): no assertion in this module reads ``final_answer``'s
content as a pass/fail signal — only its presence as a key. Every test
below shares the same adapter-shape fixture inputs from
``tests/fixtures/adapter/``; only the model script or one broken input
varies, proving one consistent invocation pattern is stable across all four
exit codes, not four unrelated scenarios.
"""

import json
from pathlib import Path

from local_agent_runner.cli import (
    EXIT_COMPLETED,
    EXIT_CONFIG_ERROR,
    EXIT_DID_NOT_CONVERGE,
    EXIT_RUNTIME_ERROR,
    main,
)
from local_agent_runner.ollama_client import ChatMessage, ChatResponse, OllamaConnectionError

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adapter"
TASK_FILE = FIXTURES_DIR / "task.md"
CONTEXT_FILE = FIXTURES_DIR / "context.md"
TOOLS_FILE = FIXTURES_DIR / "tools.json"

# §7 step 2: the shim always passes an explicit tag — deliberately not the
# CLI's own default, so a passing test can't be hiding a fallback to it.
ADAPTER_MODEL = "qwen2.5-coder:7b"

RESULT_KEYS = [
    "status",
    "final_answer",
    "transcript",
    "iterations",
    "tokens",
    "model",
    "duration_ms",
]


def adapter_argv(transcript_path, **overrides):
    """The §7 step 2 invocation shape: DoD task, scoped context, coding-set
    tools, explicit model. ``overrides`` may replace any of these paths to
    inject exactly one broken input, per the shared-fixture convention."""
    values = {
        "task": str(TASK_FILE),
        "context": str(CONTEXT_FILE),
        "tools": str(TOOLS_FILE),
        "model": ADAPTER_MODEL,
        "transcript": str(transcript_path),
    }
    values.update(overrides)
    argv = []
    for flag, value in values.items():
        argv += [f"--{flag}", str(value)]
    return argv


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


def final_answer_response(text, eval_count=12):
    return response_from({"role": "assistant", "content": text}, eval_count)


class FakeClient:
    """Message-recording fake (mirrors ``tests/test_loop.py``'s pattern):
    this module asserts on message *content* (the context-seeding order),
    not just call count, so the simpler call-counting fake from
    ``tests/test_cli.py`` is not enough here."""

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
    """Never produces a final answer — the ceiling must halt the loop under
    the same adapter-shape inputs used by the other three exit codes."""

    def __init__(self):
        self.calls = 0

    def chat(self, model, messages, tools=None, options=None):
        self.calls += 1
        return native_call_response("read_file", {"path": "/repo/README.md"})


class TestExitZeroCompleted:
    def test_completed_transcript_is_structurally_valid(self, tmp_path):
        transcript = tmp_path / "out.json"
        # Content is deliberately unassertable prose: this test proves
        # success via exit code + transcript structure only (SN-3).
        fake = FakeClient([final_answer_response("Anything, never asserted.")])

        rc = main(adapter_argv(transcript), client=fake)

        assert rc == EXIT_COMPLETED
        data = json.loads(transcript.read_text())
        assert list(data.keys()) == RESULT_KEYS  # exactly the §3 shape
        assert data["status"] == "completed"
        assert "final_answer" in data  # presence only — never its content
        assert data["model"] == ADAPTER_MODEL  # the explicit tag, not the default


class TestContextReachesModel:
    def test_context_seeded_as_system_message_ahead_of_task(self, tmp_path):
        transcript = tmp_path / "out.json"
        fake = FakeClient([final_answer_response("ok")])

        rc = main(adapter_argv(transcript), client=fake)

        assert rc == EXIT_COMPLETED
        messages = fake.calls[0]["messages"]
        assert messages == [
            {"role": "system", "content": CONTEXT_FILE.read_text()},
            {"role": "user", "content": TASK_FILE.read_text()},
        ]


class TestExitTwoDidNotConverge:
    def test_did_not_converge_transcript_still_structurally_valid(self, tmp_path):
        transcript = tmp_path / "out.json"
        client = EndlessToolCaller()

        rc = main(
            adapter_argv(transcript, **{"max-iterations": 2}),
            client=client,
        )

        assert rc == EXIT_DID_NOT_CONVERGE
        data = json.loads(transcript.read_text())
        assert list(data.keys()) == RESULT_KEYS
        assert data["status"] == "max_iterations_exceeded"


class TestExitThreeConfigError:
    def test_unreadable_context_file_under_adapter_shape(self, tmp_path):
        transcript = tmp_path / "out.json"
        broken_context = tmp_path / "missing-context.md"

        rc = main(
            adapter_argv(transcript, context=str(broken_context)),
            client=FakeClient([]),  # untouched: the loop must never start
        )

        assert rc == EXIT_CONFIG_ERROR
        assert not transcript.exists()


class TestExitFourRuntimeError:
    def test_client_failure_under_adapter_shape(self, tmp_path):
        transcript = tmp_path / "out.json"
        fake = FakeClient([OllamaConnectionError("cannot reach Ollama at X")])

        rc = main(adapter_argv(transcript), client=fake)

        assert rc == EXIT_RUNTIME_ERROR
        data = json.loads(transcript.read_text())
        assert list(data.keys()) == RESULT_KEYS
        assert data["status"] == "error"
