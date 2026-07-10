"""Unit tests for local_agent_runner.tool_calls — fully offline.

Covers both CONTRACT.md §1.2 delivery modes via E1.1's recorded fixtures
(reused unmodified) plus new edge-case fixtures, and the §1.3 argument
coercion directly.
"""

import json
from pathlib import Path

import pytest

from local_agent_runner.ollama_client import ChatMessage
from local_agent_runner.tool_calls import (
    INVALID_ARGUMENTS,
    UNKNOWN_TOOL,
    ArgumentCoercionError,
    FinalAnswer,
    RepairableError,
    ToolCallRequest,
    coerce_arguments,
    parse_tool_call,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def message_from_fixture(name):
    return ChatMessage.from_dict(load_fixture(name)["message"])


READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
    },
    "required": ["path"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": READ_FILE_SCHEMA,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


class TestNativeMode:
    def test_native_fixture_parses_to_coerced_read_file_call(self):
        # the §1.3 observed defect: llama3.1 sent "start_line": "8" (string)
        result = parse_tool_call(
            message_from_fixture("chat_native_tool_calls.json"), TOOLS
        )

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"
        assert result.arguments == {"path": "src/app.py", "start_line": 8}
        assert result.arguments["start_line"] == 8
        assert type(result.arguments["start_line"]) is int

    def test_native_call_wins_without_touching_content(self):
        # decoy content carries a *different* call; native field must win
        message = ChatMessage(
            role="assistant",
            content='{"name": "run_command", "arguments": {"command": "ls"}}',
            tool_calls=[
                {"function": {"name": "read_file", "arguments": {"path": "a.py"}}}
            ],
        )
        result = parse_tool_call(message, TOOLS)

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"

    def test_multiple_native_calls_first_only(self):
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"path": "a.py"}}},
                {"function": {"name": "run_command", "arguments": {"command": "ls"}}},
            ],
        }
        result = parse_tool_call(message, TOOLS)

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"


class TestContentMode:
    def test_fenced_call_fixture_parses_to_valid_read_file_call(self):
        # qwen2.5-coder (the default model's delivery mode): ```json fence
        result = parse_tool_call(
            message_from_fixture("chat_content_embedded_tool_call.json"), TOOLS
        )

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"
        assert result.arguments == {"path": "src/app.py"}

    def test_fence_surrounded_by_prose_is_extracted_and_coerced(self):
        result = parse_tool_call(
            message_from_fixture("chat_content_fenced_with_prose.json"), TOOLS
        )

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"
        assert result.arguments == {"path": "src/app.py", "start_line": 8}

    def test_bare_object_as_whole_content(self):
        result = parse_tool_call(
            message_from_fixture("chat_content_bare_object_tool_call.json"), TOOLS
        )

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"
        assert result.arguments == {"path": "src/app.py", "start_line": 3}

    def test_plain_dict_message_is_accepted(self):
        message = {
            "role": "assistant",
            "content": '{"name": "read_file", "arguments": {"path": "x.py"}}',
        }
        result = parse_tool_call(message, TOOLS)

        assert isinstance(result, ToolCallRequest)
        assert result.name == "read_file"


class TestFinalAnswer:
    def test_plain_text_fixture_is_final_answer(self):
        result = parse_tool_call(
            message_from_fixture("chat_final_answer.json"), TOOLS
        )

        assert isinstance(result, FinalAnswer)
        assert result.content == "The edit is complete and the test passes."

    def test_invalid_json_in_fence_is_final_answer_not_error(self):
        # settled in the spec: unparseable text is an answer (§5 step 4)
        fixture = load_fixture("chat_content_fence_invalid_json.json")
        result = parse_tool_call(ChatMessage.from_dict(fixture["message"]), TOOLS)

        assert isinstance(result, FinalAnswer)
        assert result.content == fixture["message"]["content"]

    def test_valid_json_that_is_not_a_call_is_final_answer(self):
        message = {"role": "assistant", "content": '{"answer": 42}'}
        result = parse_tool_call(message, TOOLS)

        assert isinstance(result, FinalAnswer)
        assert result.content == '{"answer": 42}'

    def test_empty_content_and_no_tool_calls_is_final_answer(self):
        result = parse_tool_call({"role": "assistant", "content": ""}, TOOLS)

        assert isinstance(result, FinalAnswer)
        assert result.content == ""


class TestRepairableErrors:
    def test_unknown_tool_names_it_and_lists_enabled_tools(self):
        result = parse_tool_call(
            message_from_fixture("chat_native_unknown_tool.json"), TOOLS
        )

        assert isinstance(result, RepairableError)
        assert result.kind == UNKNOWN_TOOL
        assert "delete_file" in result.message
        assert "read_file" in result.message
        assert "run_command" in result.message

    def test_missing_required_argument(self):
        result = parse_tool_call(
            message_from_fixture("chat_native_missing_required_argument.json"),
            TOOLS,
        )

        assert isinstance(result, RepairableError)
        assert result.kind == INVALID_ARGUMENTS
        assert "path" in result.message

    def test_uncoercible_argument(self):
        result = parse_tool_call(
            message_from_fixture("chat_native_uncoercible_argument.json"), TOOLS
        )

        assert isinstance(result, RepairableError)
        assert result.kind == INVALID_ARGUMENTS
        assert "start_line" in result.message

    def test_content_mode_calls_are_validated_too(self):
        message = {
            "role": "assistant",
            "content": '```json\n{"name": "format_disk", "arguments": {}}\n```',
        }
        result = parse_tool_call(message, TOOLS)

        assert isinstance(result, RepairableError)
        assert result.kind == UNKNOWN_TOOL

    def test_outcomes_are_a_closed_type_routable_set(self):
        # E1.4 routes on types alone — the three outcomes are distinct types
        # and the repair outcome carries a ready-to-send message + kind
        outcomes = {
            type(parse_tool_call(message_from_fixture(f), TOOLS))
            for f in (
                "chat_native_tool_calls.json",
                "chat_final_answer.json",
                "chat_native_unknown_tool.json",
            )
        }
        assert outcomes == {ToolCallRequest, FinalAnswer, RepairableError}


class TestCoerceArguments:
    def test_string_integer_is_coerced(self):
        result = coerce_arguments(
            {"path": "a.py", "start_line": "8"}, READ_FILE_SCHEMA
        )
        assert result["start_line"] == 8
        assert type(result["start_line"]) is int

    def test_string_number_is_coerced(self):
        schema = {"type": "object", "properties": {"ratio": {"type": "number"}}}
        assert coerce_arguments({"ratio": "1.5"}, schema) == {"ratio": 1.5}

    @pytest.mark.parametrize(
        "raw,expected",
        [("true", True), ("false", False), ("True", True), ("FALSE", False)],
    )
    def test_string_boolean_is_coerced_case_insensitively(self, raw, expected):
        schema = {"type": "object", "properties": {"flag": {"type": "boolean"}}}
        assert coerce_arguments({"flag": raw}, schema) == {"flag": expected}

    def test_correct_types_pass_through_unchanged(self):
        schema = {
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "x": {"type": "number"},
                "b": {"type": "boolean"},
                "s": {"type": "string"},
            },
        }
        args = {"n": 8, "x": 1.5, "b": True, "s": "8"}
        assert coerce_arguments(args, schema) == args

    def test_string_properties_are_never_coerced(self):
        schema = {"type": "object", "properties": {"s": {"type": "string"}}}
        result = coerce_arguments({"s": "8"}, schema)
        assert result == {"s": "8"}
        assert type(result["s"]) is str

    def test_uncoercible_integer_raises_invalid_arguments(self):
        with pytest.raises(ArgumentCoercionError) as excinfo:
            coerce_arguments({"path": "a.py", "start_line": "abc"}, READ_FILE_SCHEMA)
        assert "start_line" in str(excinfo.value)

    def test_missing_required_property_raises(self):
        with pytest.raises(ArgumentCoercionError) as excinfo:
            coerce_arguments({"start_line": 1}, READ_FILE_SCHEMA)
        assert "path" in str(excinfo.value)

    def test_properties_not_in_schema_pass_through_untouched(self):
        result = coerce_arguments(
            {"path": "a.py", "encoding": "utf-8"}, READ_FILE_SCHEMA
        )
        assert result["encoding"] == "utf-8"

    def test_original_arguments_dict_is_not_mutated(self):
        args = {"path": "a.py", "start_line": "8"}
        coerce_arguments(args, READ_FILE_SCHEMA)
        assert args["start_line"] == "8"
