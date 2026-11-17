"""Offline tests for pluggable custom tool handlers (CONTRACT §2, §10.1).

The proving vehicle is ``examples/hello_world_tool.py``: imported as a
normal module and driven through the real ``run()`` loop by a scripted
fake model, in both §1.2 delivery modes.
"""

from __future__ import annotations  # also proves string annotations are resolved

import importlib.util
import json
from pathlib import Path

import pytest

from local_agent_runner import (
    STATUS_COMPLETED,
    CustomTool,
    ToolPermissions,
    ToolResult,
    custom_tool,
    run,
)
from local_agent_runner.custom_tools import execute_custom_tool, index_custom_tools
from local_agent_runner.ollama_client import ChatMessage, ChatResponse

EXAMPLES = Path(__file__).parent.parent / "examples"


def load_example(module_name="hello_world_tool"):
    path = EXAMPLES / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hello_world():
    return load_example("hello_world_tool").hello_world


@pytest.fixture(scope="module")
def goodbye_world():
    return load_example("goodbye_world_tool").goodbye_world


# ---------------------------------------------------------------------------
# Scripted fake model
# ---------------------------------------------------------------------------


def _response(message, eval_count=10):
    return ChatResponse(
        message=ChatMessage.from_dict(message),
        eval_count=eval_count,
        prompt_eval_count=None,
        raw={"message": message},
    )


def native_call(name, arguments):
    return _response(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    )


def content_call(name, arguments):
    call = json.dumps({"name": name, "arguments": arguments})
    return _response(
        {"role": "assistant", "content": f"Calling it.\n```json\n{call}\n```", "tool_calls": []}
    )


def final(text):
    return _response({"role": "assistant", "content": text})


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, model, messages, tools=None, options=None):
        self.calls.append(
            {
                "messages": [m.to_dict() if isinstance(m, ChatMessage) else m for m in messages],
                "tools": tools,
            }
        )
        return self.script.pop(0)


# ---------------------------------------------------------------------------
# The hello_world example: definition and direct use
# ---------------------------------------------------------------------------


def test_hello_world_is_a_custom_tool(hello_world):
    assert isinstance(hello_world, CustomTool)
    assert hello_world.definition() == {
        "type": "function",
        "function": {
            "name": "hello_world",
            "description": "Return a greeting for someone. Pass 'name' as the person to greet.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    }


def test_hello_world_still_callable_as_plain_function(hello_world):
    assert hello_world("Ada").startswith("Hello, Ada!")
    assert hello_world(name="Ada").startswith("Hello, Ada!")


# ---------------------------------------------------------------------------
# hello_world through the real run() loop
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("call", [native_call, content_call], ids=["native", "content"])
def test_run_executes_hello_world(hello_world, call):
    client = FakeClient([call("hello_world", {"name": "Ada"}), final("Hello, Ada!")])

    result = run(
        "any-model", "Greet Ada.", ToolPermissions(), client=client, custom_tools=[hello_world]
    )

    assert result.status == STATUS_COMPLETED
    assert result.final_answer == "Hello, Ada!"
    # The model was offered exactly the custom tool.
    assert client.calls[0]["tools"] == [hello_world.definition()]
    # The handler ran and its output was fed back as the tool message.
    expected = "Hello, Ada! Greetings from a custom local-agent-runner tool."
    assert client.calls[1]["messages"][-1] == {"role": "tool", "content": expected}
    assert result.iterations == 1
    step = result.transcript[0]
    assert step["tool_call"] == {"name": "hello_world", "args": {"name": "Ada"}}
    assert step["tool_result"] == expected


def test_custom_tools_sit_alongside_enabled_builtins(hello_world, tmp_path):
    target = tmp_path / "who.txt"
    target.write_text("Grace")
    perms = ToolPermissions(enabled=["read_file"], allow_paths=[str(tmp_path) + "/**"])
    client = FakeClient(
        [
            native_call("read_file", {"path": str(target)}),
            native_call("hello_world", {"name": "Grace"}),
            final("done"),
        ]
    )

    result = run("m", "t", perms, client=client, custom_tools=[hello_world])

    names = [d["function"]["name"] for d in client.calls[0]["tools"]]
    assert names == ["read_file", "hello_world"]
    assert [s["tool_result"] for s in result.transcript] == [
        "Grace",
        "Hello, Grace! Greetings from a custom local-agent-runner tool.",
    ]


def test_missing_argument_is_repaired_not_crashed(hello_world):
    client = FakeClient(
        [native_call("hello_world", {}), native_call("hello_world", {"name": "Ada"}), final("ok")]
    )

    result = run("m", "t", ToolPermissions(), client=client, custom_tools=[hello_world])

    assert result.status == STATUS_COMPLETED
    assert "missing required argument(s): 'name'" in result.transcript[0]["tool_result"]
    assert result.transcript[1]["tool_result"].startswith("Hello, Ada!")


def test_arguments_are_coerced_against_inferred_schema():
    @custom_tool
    def repeat(word: str, times: int, shout: bool = False) -> str:
        """Repeat a word."""
        out = " ".join([word] * times)
        return out.upper() if shout else out

    client = FakeClient(
        [native_call("repeat", {"word": "hi", "times": "3", "shout": "true"}), final("ok")]
    )
    result = run("m", "t", ToolPermissions(), client=client, custom_tools=[repeat])
    assert result.transcript[0]["tool_result"] == "HI HI HI"


def test_handler_exception_becomes_tool_error_feedback():
    @custom_tool
    def boom() -> str:
        """Always fails."""
        raise RuntimeError("kaboom")

    client = FakeClient([native_call("boom", {}), final("gave up")])
    result = run("m", "t", ToolPermissions(), client=client, custom_tools=[boom])
    assert result.status == STATUS_COMPLETED
    assert result.transcript[0]["tool_result"] == (
        "boom: unexpected error while executing: RuntimeError: kaboom"
    )


def test_no_custom_tools_leaves_behavior_unchanged():
    client = FakeClient([final("plain")])
    result = run("m", "t", ToolPermissions(), client=client)
    assert result.final_answer == "plain"
    assert client.calls[0]["tools"] == []


# ---------------------------------------------------------------------------
# Registration rules (caller mistakes fail before the first model call)
# ---------------------------------------------------------------------------


def test_name_colliding_with_builtin_is_rejected():
    @custom_tool(name="read_file")
    def fake(path: str) -> str:
        """Shadow attempt."""
        return ""

    client = FakeClient([])
    with pytest.raises(ValueError, match="collides with a built-in"):
        run("m", "t", ToolPermissions(), client=client, custom_tools=[fake])
    assert client.calls == []


def test_duplicate_names_are_rejected(hello_world):
    with pytest.raises(ValueError, match="duplicate"):
        index_custom_tools([hello_world, hello_world])


def test_plain_function_is_rejected():
    def not_wrapped(name: str) -> str:
        return name

    with pytest.raises(TypeError, match="use @custom_tool"):
        index_custom_tools([not_wrapped])


# ---------------------------------------------------------------------------
# @custom_tool schema inference and validation
# ---------------------------------------------------------------------------


def test_inferred_schema_types_and_required():
    @custom_tool
    def f(a: str, b: int, c: float, d: bool = True) -> str:
        """Doc line.

        More detail."""
        return ""

    fn = f.definition()["function"]
    assert fn["description"] == "Doc line.\n\nMore detail."
    assert fn["parameters"] == {
        "type": "object",
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "integer"},
            "c": {"type": "number"},
            "d": {"type": "boolean"},
        },
        "required": ["a", "b", "c"],
    }


def test_explicit_overrides():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Who to greet."}},
        "required": ["name"],
    }

    @custom_tool(name="greet", description="Greets.", parameters=schema)
    def anything(**kwargs):
        return "hi"

    fn = anything.definition()["function"]
    assert (fn["name"], fn["description"], fn["parameters"]) == ("greet", "Greets.", schema)


@pytest.mark.parametrize(
    "source, error",
    [
        ("def f(x: str):\n    return x", ValueError),  # no docstring
        ("def f(x: list):\n    'd'\n    return x", TypeError),  # unsupported type
        ("def f(x):\n    'd'\n    return x", TypeError),  # unannotated
        ("def f(*xs: str):\n    'd'\n    return xs", TypeError),  # *args
    ],
)
def test_bad_signatures_fail_at_decoration(source, error):
    namespace = {}
    exec(source, namespace)
    with pytest.raises(error):
        custom_tool(namespace["f"])


def test_bad_name_is_rejected():
    with pytest.raises(ValueError, match="invalid custom tool name"):
        CustomTool("has space", "d", {"type": "object", "properties": {}}, lambda: "")


# ---------------------------------------------------------------------------
# execute_custom_tool return-value handling
# ---------------------------------------------------------------------------


def _tool(fn):
    return CustomTool(fn.__name__, "d", {"type": "object", "properties": {}}, fn)


def test_return_values_are_normalized():
    def as_str():
        return "text"

    def as_result():
        return ToolResult(ok=False, output="custom failure")

    def as_dict():
        return {"greeting": "hi", "count": 2}

    assert execute_custom_tool(_tool(as_str), {}) == ToolResult(True, "text")
    assert execute_custom_tool(_tool(as_result), {}) == ToolResult(False, "custom failure")
    assert execute_custom_tool(_tool(as_dict), {}) == ToolResult(
        True, '{"greeting": "hi", "count": 2}'
    )


def test_unexpected_argument_becomes_error_result(hello_world):
    outcome = execute_custom_tool(hello_world, {"name": "Ada", "extra": 1})
    assert outcome.ok is False
    assert outcome.output.startswith("hello_world: unexpected error while executing: TypeError")


# ---------------------------------------------------------------------------
# Two custom tools together: hello_world + goodbye_world
#
# They come from separate modules and share the argument name ``name``, so
# these tests pass only if calls are routed by tool name and neither tool
# leaks into or shadows the other.
# ---------------------------------------------------------------------------

HELLO_ADA = "Hello, Ada! Greetings from a custom local-agent-runner tool."
GOODBYE_ADA = "Goodbye, Ada! See you next run."


def tool_names(tools):
    return [d["function"]["name"] for d in tools]


def test_goodbye_world_is_an_independent_custom_tool(goodbye_world, hello_world):
    assert isinstance(goodbye_world, CustomTool)
    assert goodbye_world("Ada") == GOODBYE_ADA
    assert goodbye_world.name != hello_world.name
    assert goodbye_world.handler is not hello_world.handler
    # Same argument shape on purpose: routing can't rely on arguments.
    assert (
        goodbye_world.definition()["function"]["parameters"]
        == hello_world.definition()["function"]["parameters"]
    )


def test_both_tools_are_offered_in_registration_order(hello_world, goodbye_world):
    for registered in ([hello_world, goodbye_world], [goodbye_world, hello_world]):
        client = FakeClient([final("ok")])
        run("m", "t", ToolPermissions(), client=client, custom_tools=registered)
        assert client.calls[0]["tools"] == [t.definition() for t in registered]


@pytest.mark.parametrize("call", [native_call, content_call], ids=["native", "content"])
def test_each_call_is_routed_to_its_own_handler(hello_world, goodbye_world, call):
    client = FakeClient(
        [
            call("hello_world", {"name": "Ada"}),
            call("goodbye_world", {"name": "Ada"}),
            final("both done"),
        ]
    )

    result = run(
        "m", "t", ToolPermissions(), client=client, custom_tools=[hello_world, goodbye_world]
    )

    assert result.status == STATUS_COMPLETED
    assert result.iterations == 2
    assert [(s["tool_call"]["name"], s["tool_result"]) for s in result.transcript] == [
        ("hello_world", HELLO_ADA),
        ("goodbye_world", GOODBYE_ADA),
    ]
    # The model saw each tool's own output fed back in order.
    assert client.calls[1]["messages"][-1] == {"role": "tool", "content": HELLO_ADA}
    assert client.calls[2]["messages"][-1] == {"role": "tool", "content": GOODBYE_ADA}


def test_routing_is_independent_of_registration_order(hello_world, goodbye_world):
    client = FakeClient(
        [
            native_call("goodbye_world", {"name": "Ada"}),
            native_call("hello_world", {"name": "Ada"}),
            final("ok"),
        ]
    )
    result = run(
        "m", "t", ToolPermissions(), client=client, custom_tools=[goodbye_world, hello_world]
    )
    assert [s["tool_result"] for s in result.transcript] == [GOODBYE_ADA, HELLO_ADA]


def test_interleaved_repeated_calls_do_not_bleed(hello_world, goodbye_world):
    client = FakeClient(
        [
            native_call("hello_world", {"name": "Ada"}),
            native_call("goodbye_world", {"name": "Grace"}),
            native_call("hello_world", {"name": "Linus"}),
            native_call("goodbye_world", {"name": "Ada"}),
            final("ok"),
        ]
    )
    result = run(
        "m", "t", ToolPermissions(), client=client, custom_tools=[hello_world, goodbye_world]
    )
    assert [s["tool_result"].split("!")[0] for s in result.transcript] == [
        "Hello, Ada",
        "Goodbye, Grace",
        "Hello, Linus",
        "Goodbye, Ada",
    ]


def test_both_custom_tools_alongside_a_builtin(hello_world, goodbye_world, tmp_path):
    target = tmp_path / "who.txt"
    target.write_text("Ada")
    perms = ToolPermissions(enabled=["read_file"], allow_paths=[str(tmp_path) + "/**"])
    client = FakeClient(
        [
            native_call("read_file", {"path": str(target)}),
            native_call("hello_world", {"name": "Ada"}),
            native_call("goodbye_world", {"name": "Ada"}),
            final("ok"),
        ]
    )

    result = run("m", "t", perms, client=client, custom_tools=[hello_world, goodbye_world])

    assert tool_names(client.calls[0]["tools"]) == ["read_file", "hello_world", "goodbye_world"]
    assert [s["tool_result"] for s in result.transcript] == ["Ada", HELLO_ADA, GOODBYE_ADA]


def test_failure_in_one_tool_does_not_affect_the_other(hello_world, goodbye_world):
    client = FakeClient(
        [
            native_call("goodbye_world", {}),  # missing 'name' -> repair feedback
            native_call("hello_world", {"name": "Ada"}),
            native_call("goodbye_world", {"name": "Ada"}),
            final("ok"),
        ]
    )
    result = run(
        "m", "t", ToolPermissions(), client=client, custom_tools=[hello_world, goodbye_world]
    )
    results = [s["tool_result"] for s in result.transcript]
    assert "invalid arguments for tool 'goodbye_world'" in results[0]
    assert results[1:] == [HELLO_ADA, GOODBYE_ADA]


def test_unknown_tool_repair_lists_both_custom_tools(hello_world, goodbye_world):
    client = FakeClient([native_call("hello_goodbye", {"name": "Ada"}), final("ok")])
    result = run(
        "m", "t", ToolPermissions(), client=client, custom_tools=[hello_world, goodbye_world]
    )
    assert result.transcript[0]["tool_result"] == (
        "unknown tool 'hello_goodbye'. The enabled tools are: goodbye_world, hello_world."
    )


def test_registering_one_tool_does_not_expose_the_other(hello_world, goodbye_world):
    # No global registry: importing goodbye_world's module doesn't enable it.
    client = FakeClient([native_call("goodbye_world", {"name": "Ada"}), final("ok")])
    result = run("m", "t", ToolPermissions(), client=client, custom_tools=[hello_world])
    assert tool_names(client.calls[0]["tools"]) == ["hello_world"]
    assert result.transcript[0]["tool_result"].startswith("unknown tool 'goodbye_world'")


def test_multi_tool_proof_script_passes_offline(monkeypatch, capsys):
    """Run examples/multi_tool_proof.py's main() against the fake model."""
    monkeypatch.syspath_prepend(str(EXAMPLES))
    proof = load_example("multi_tool_proof")
    client = FakeClient(
        [
            content_call("hello_world", {"name": "Ada"}),
            content_call("goodbye_world", {"name": "Ada"}),
            final(f"{HELLO_ADA} {GOODBYE_ADA}"),
        ]
    )
    real_run = proof.run
    monkeypatch.setattr(proof, "run", lambda *a, **kw: real_run(*a, client=client, **kw))

    assert proof.main([]) == 0
    assert "PROOF OK" in capsys.readouterr().err
    assert tool_names(client.calls[0]["tools"]) == ["hello_world", "goodbye_world"]


def test_multi_tool_proof_script_fails_if_a_tool_is_skipped(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    proof = load_example("multi_tool_proof")
    client = FakeClient([native_call("hello_world", {"name": "Ada"}), final(HELLO_ADA)])
    real_run = proof.run
    monkeypatch.setattr(proof, "run", lambda *a, **kw: real_run(*a, client=client, **kw))

    assert proof.main([]) == 1
    assert "PROOF FAILED" in capsys.readouterr().err
