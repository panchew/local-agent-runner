"""Unit tests for local_agent_runner.tools — fully offline.

No GPU, no Ollama, no network: everything runs against pytest ``tmp_path``
fixtures and innocuous commands (``echo``, ``python3 -c ...``, a short
sleep for the timeout case). ``subprocess`` use is expected here — the rule
is *never invoke ollama*, not *never subprocess*.
"""

from pathlib import Path

from local_agent_runner.tool_calls import ToolCallRequest, parse_tool_call
from local_agent_runner.tools import (
    OUTPUT_CAP,
    ToolPermissions,
    ToolResult,
    execute_tool,
    tool_definitions,
)


def perms_for(tmp_path, **overrides):
    """Permissions allowing everything under tmp_path plus test commands."""
    data = {
        "enabled": ["read_file", "edit_file", "run_command"],
        "allow_paths": [str(tmp_path / "**")],
        "allow_commands": ["echo *", "python3 -c *", "sleep *"],
    }
    data.update(overrides)
    return ToolPermissions.from_dict(data)


# ---------------------------------------------------------------------------
# ToolPermissions
# ---------------------------------------------------------------------------


class TestToolPermissions:
    def test_from_dict_on_contract_example_shape(self):
        # The exact §4 tools.json example from CONTRACT.md.
        perms = ToolPermissions.from_dict(
            {
                "enabled": ["read_file", "write_file", "run_command"],
                "allow_paths": ["/repo/**"],
                "allow_commands": ["npm test", "npm run lint", "pytest*"],
                "timeout": 120,
            }
        )
        assert perms.enabled == ["read_file", "write_file", "run_command"]
        assert perms.allow_paths == ["/repo/**"]
        assert perms.allow_commands == ["npm test", "npm run lint", "pytest*"]
        assert perms.deny_commands == []
        assert perms.timeout == 120

    def test_from_dict_defaults(self):
        perms = ToolPermissions.from_dict({})
        assert perms.enabled == []
        assert perms.allow_paths == []
        assert perms.allow_commands == []
        assert perms.deny_commands == []
        assert perms.timeout == 120

    def test_paths_denied_by_default(self, tmp_path):
        perms = ToolPermissions.from_dict({})
        assert not perms.path_permitted(tmp_path / "any.txt")

    def test_commands_denied_by_default(self):
        perms = ToolPermissions.from_dict({})
        assert not perms.command_permitted("echo hi")

    def test_deny_pattern_wins_over_allow(self):
        perms = ToolPermissions.from_dict(
            {
                "allow_commands": ["pytest*"],
                "deny_commands": ["pytest*slow*"],
            }
        )
        assert perms.command_permitted("pytest tests/test_fast.py")
        assert not perms.command_permitted("pytest tests/test_slow.py")


# ---------------------------------------------------------------------------
# Tool definitions (wire format)
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_filtered_by_enabled(self, tmp_path):
        perms = perms_for(tmp_path, enabled=["read_file", "run_command"])
        names = [d["function"]["name"] for d in tool_definitions(perms)]
        assert names == ["read_file", "run_command"]

    def test_unknown_enabled_names_ignored(self, tmp_path):
        perms = perms_for(tmp_path, enabled=["git", "edit_file"])
        names = [d["function"]["name"] for d in tool_definitions(perms)]
        assert names == ["edit_file"]

    def test_new_tools_appear_in_canonical_order_when_enabled(self, tmp_path):
        perms = perms_for(
            tmp_path,
            enabled=["read_file", "write_file", "edit_file", "list_dir", "run_command"],
        )
        names = [d["function"]["name"] for d in tool_definitions(perms)]
        assert names == ["read_file", "write_file", "edit_file", "list_dir", "run_command"]

    def test_required_lists_and_flat_primitive_schemas(self, tmp_path):
        defs = {
            d["function"]["name"]: d["function"]["parameters"]
            for d in tool_definitions(
                perms_for(
                    tmp_path,
                    enabled=[
                        "read_file",
                        "write_file",
                        "edit_file",
                        "list_dir",
                        "run_command",
                    ],
                )
            )
        }
        assert defs["read_file"]["required"] == ["path"]
        assert defs["write_file"]["required"] == ["path", "content"]
        assert defs["edit_file"]["required"] == ["path", "old", "new"]
        assert defs["list_dir"]["required"] == ["path"]
        assert defs["run_command"]["required"] == ["command"]
        for schema in defs.values():
            assert schema["type"] == "object"
            for prop in schema["properties"].values():
                # Flat primitive types only — E1.2's coercion scope.
                assert prop["type"] in {"string", "integer", "number", "boolean"}
                assert prop["description"]

    def test_definitions_have_model_facing_descriptions(self, tmp_path):
        for definition in tool_definitions(perms_for(tmp_path)):
            assert definition["type"] == "function"
            assert definition["function"]["description"]


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    def test_full_read(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line one\nline two\n")
        result = execute_tool("read_file", {"path": str(f)}, perms_for(tmp_path))
        assert result.ok
        assert result.output == "line one\nline two\n"

    def test_line_range_read(self, tmp_path):
        f = tmp_path / "nums.txt"
        f.write_text("1\n2\n3\n4\n5\n")
        result = execute_tool(
            "read_file",
            {"path": str(f), "start_line": 2, "end_line": 4},
            perms_for(tmp_path),
        )
        assert result.ok
        assert result.output == "2\n3\n4\n"

    def test_bad_range_is_error(self, tmp_path):
        f = tmp_path / "nums.txt"
        f.write_text("1\n2\n")
        result = execute_tool(
            "read_file",
            {"path": str(f), "start_line": 5, "end_line": 9},
            perms_for(tmp_path),
        )
        assert not result.ok
        assert "invalid line range" in result.output

    def test_path_outside_allow_paths_denied(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        perms = perms_for(tmp_path, allow_paths=[str(allowed / "**")])
        result = execute_tool("read_file", {"path": str(outside)}, perms)
        assert not result.ok
        assert "denied" in result.output

    def test_traversal_resolving_outside_globs_denied(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("secret")
        perms = perms_for(tmp_path, allow_paths=[str(allowed / "**")])
        sneaky = str(allowed / ".." / "secret.txt")
        result = execute_tool("read_file", {"path": sneaky}, perms)
        assert not result.ok
        assert "denied" in result.output
        assert "secret" != result.output  # file content never leaks

    def test_missing_file_is_error(self, tmp_path):
        result = execute_tool(
            "read_file", {"path": str(tmp_path / "gone.txt")}, perms_for(tmp_path)
        )
        assert not result.ok
        assert "does not exist" in result.output


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


class TestEditFile:
    def test_single_replacement_written_to_disk(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("VALUE = 41\nOTHER = 7\n")
        result = execute_tool(
            "edit_file",
            {"path": str(f), "old": "VALUE = 41", "new": "VALUE = 42"},
            perms_for(tmp_path),
        )
        assert result.ok
        assert f.read_text() == "VALUE = 42\nOTHER = 7\n"

    def test_old_not_found_is_distinct_error(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("VALUE = 41\n")
        result = execute_tool(
            "edit_file",
            {"path": str(f), "old": "MISSING", "new": "X"},
            perms_for(tmp_path),
        )
        assert not result.ok
        assert "not found" in result.output
        assert f.read_text() == "VALUE = 41\n"

    def test_old_ambiguous_is_distinct_error(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("x = 1\nx = 1\n")
        result = execute_tool(
            "edit_file",
            {"path": str(f), "old": "x = 1", "new": "x = 2"},
            perms_for(tmp_path),
        )
        assert not result.ok
        assert "2 times" in result.output
        assert "exactly once" in result.output
        assert result.output != execute_tool(
            "edit_file",
            {"path": str(f), "old": "MISSING", "new": "x"},
            perms_for(tmp_path),
        ).output  # not-found and ambiguous are distinct messages
        assert f.read_text() == "x = 1\nx = 1\n"

    def test_denied_path_is_error(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("VALUE = 41\n")
        perms = perms_for(tmp_path, allow_paths=[])
        result = execute_tool(
            "edit_file",
            {"path": str(f), "old": "41", "new": "42"},
            perms,
        )
        assert not result.ok
        assert "denied" in result.output
        assert f.read_text() == "VALUE = 41\n"

    def test_missing_file_is_error(self, tmp_path):
        result = execute_tool(
            "edit_file",
            {"path": str(tmp_path / "gone.py"), "old": "a", "new": "b"},
            perms_for(tmp_path),
        )
        assert not result.ok
        assert "does not exist" in result.output


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


class TestWriteFile:
    def test_creates_new_file(self, tmp_path):
        f = tmp_path / "new.txt"
        result = execute_tool(
            "write_file", {"path": str(f), "content": "hello\n"}, perms_for(tmp_path)
        )
        assert result.ok
        assert f.read_text() == "hello\n"
        assert "wrote 6 characters" in result.output

    def test_overwrites_existing_file(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old content\n")
        result = execute_tool(
            "write_file", {"path": str(f), "content": "new\n"}, perms_for(tmp_path)
        )
        assert result.ok
        assert f.read_text() == "new\n"

    def test_creates_missing_parent_directories(self, tmp_path):
        f = tmp_path / "a" / "b" / "c.txt"
        result = execute_tool(
            "write_file", {"path": str(f), "content": "deep\n"}, perms_for(tmp_path)
        )
        assert result.ok
        assert f.read_text() == "deep\n"

    def test_denied_path_is_error(self, tmp_path):
        perms = perms_for(tmp_path, allow_paths=[])
        result = execute_tool(
            "write_file",
            {"path": str(tmp_path / "f.txt"), "content": "x"},
            perms,
        )
        assert not result.ok
        assert "denied" in result.output
        assert not (tmp_path / "f.txt").exists()

    def test_target_is_directory_is_error(self, tmp_path):
        d = tmp_path / "adir"
        d.mkdir()
        result = execute_tool(
            "write_file", {"path": str(d), "content": "x"}, perms_for(tmp_path)
        )
        assert not result.ok
        assert "is a directory" in result.output

    def test_non_string_content_is_error(self, tmp_path):
        result = execute_tool(
            "write_file",
            {"path": str(tmp_path / "f.txt"), "content": 42},
            perms_for(tmp_path),
        )
        assert not result.ok
        assert "must be a string" in result.output
        assert not (tmp_path / "f.txt").exists()


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


class TestListDir:
    def test_lists_sorted_entries_with_dir_suffix(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "b.txt").write_text("b")
        (root / "a.txt").write_text("a")
        (root / "zdir").mkdir()
        result = execute_tool(
            "list_dir", {"path": str(root)}, perms_for(tmp_path)
        )
        assert result.ok
        assert result.output == "a.txt\nb.txt\nzdir/"

    def test_empty_directory_returns_fixed_message(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = execute_tool(
            "list_dir", {"path": str(empty)}, perms_for(tmp_path)
        )
        assert result.ok
        assert result.output == f"list_dir: '{empty}' is empty."

    def test_denied_path_is_error(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        perms = perms_for(tmp_path, allow_paths=[str(allowed / "**")])
        result = execute_tool("list_dir", {"path": str(outside)}, perms)
        assert not result.ok
        assert "denied" in result.output

    def test_missing_directory_is_error(self, tmp_path):
        result = execute_tool(
            "list_dir", {"path": str(tmp_path / "gone")}, perms_for(tmp_path)
        )
        assert not result.ok
        assert "does not exist" in result.output

    def test_path_is_a_file_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = execute_tool("list_dir", {"path": str(f)}, perms_for(tmp_path))
        assert not result.ok
        assert "not a directory" in result.output

    def test_output_cap_enforced(self, tmp_path):
        big = tmp_path / "many"
        big.mkdir()
        for i in range(2000):
            (big / f"file_{i:05d}.txt").write_text("x")
        result = execute_tool("list_dir", {"path": str(big)}, perms_for(tmp_path))
        assert result.ok
        assert "[truncated:" in result.output
        assert len(result.output) < OUTPUT_CAP + 200


# ---------------------------------------------------------------------------
# allow_paths consistency across all four file tools
# ---------------------------------------------------------------------------


class TestFileToolsPathConsistency:
    def test_out_of_allow_paths_denied_identically(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        perms = perms_for(tmp_path, allow_paths=[str(allowed / "**")])

        calls = {
            "read_file": {"path": str(outside)},
            "edit_file": {"path": str(outside), "old": "a", "new": "b"},
            "write_file": {"path": str(outside), "content": "x"},
            "list_dir": {"path": str(tmp_path)},
        }
        for name, arguments in calls.items():
            result = execute_tool(name, arguments, perms)
            assert not result.ok
            assert "denied" in result.output

    def test_traversal_path_denied_identically(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("secret")
        perms = perms_for(tmp_path, allow_paths=[str(allowed / "**")])
        sneaky = str(allowed / ".." / "secret.txt")

        calls = {
            "read_file": {"path": sneaky},
            "edit_file": {"path": sneaky, "old": "a", "new": "b"},
            "write_file": {"path": sneaky, "content": "x"},
            "list_dir": {"path": sneaky},
        }
        for name, arguments in calls.items():
            result = execute_tool(name, arguments, perms)
            assert not result.ok
            assert "denied" in result.output


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_allowed_command_runs(self, tmp_path):
        result = execute_tool(
            "run_command", {"command": "echo hello"}, perms_for(tmp_path)
        )
        assert result.ok
        assert "exit_code: 0" in result.output
        assert "hello" in result.output
        assert "stdout:" in result.output
        assert "stderr:" in result.output

    def test_nonzero_exit_is_successful_result(self, tmp_path):
        result = execute_tool(
            "run_command",
            {"command": "python3 -c 'import sys; sys.exit(3)'"},
            perms_for(tmp_path),
        )
        assert result.ok  # a failing command is information, not a failure
        assert "exit_code: 3" in result.output

    def test_command_matching_no_allow_pattern_denied(self, tmp_path):
        result = execute_tool(
            "run_command", {"command": "rm -rf /"}, perms_for(tmp_path)
        )
        assert not result.ok
        assert "denied" in result.output

    def test_deny_pattern_wins_even_when_allowed(self, tmp_path):
        perms = perms_for(tmp_path, deny_commands=["echo *danger*"])
        allowed = execute_tool(
            "run_command", {"command": "echo safe"}, perms
        )
        denied = execute_tool(
            "run_command", {"command": "echo danger"}, perms
        )
        assert allowed.ok
        assert not denied.ok
        assert "denied" in denied.output

    def test_timeout_returns_error_result(self, tmp_path):
        perms = perms_for(tmp_path, timeout=1)
        result = execute_tool("run_command", {"command": "sleep 5"}, perms)
        assert not result.ok
        assert "timed out after 1 seconds" in result.output

    def test_output_cap_enforced(self, tmp_path):
        result = execute_tool(
            "run_command",
            {"command": "python3 -c 'print(\"x\" * 10000)'"},
            perms_for(tmp_path),
        )
        assert result.ok
        assert "[truncated:" in result.output
        # exit_code + both capped streams + markers stay well under 2x cap.
        assert len(result.output) < 2 * OUTPUT_CAP + 200


# ---------------------------------------------------------------------------
# execute_tool surface (never raises, deterministic errors)
# ---------------------------------------------------------------------------


class TestExecuteToolSurface:
    def test_unknown_tool_is_error_result(self, tmp_path):
        result = execute_tool("delete_file", {"path": "x"}, perms_for(tmp_path))
        assert isinstance(result, ToolResult)
        assert not result.ok
        assert "unknown tool 'delete_file'" in result.output
        assert (
            "read_file, write_file, edit_file, list_dir, run_command"
            in result.output
        )

    def test_unexpected_exception_becomes_error_result(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\xff\xfe\xfa")  # not valid UTF-8 → read_text raises
        result = execute_tool("read_file", {"path": str(f)}, perms_for(tmp_path))
        assert not result.ok
        assert "unexpected error" in result.output

    def test_non_string_argument_is_error_result(self, tmp_path):
        result = execute_tool("read_file", {"path": 42}, perms_for(tmp_path))
        assert not result.ok
        assert "must be a string" in result.output

    def test_same_denial_twice_is_byte_identical(self, tmp_path):
        perms = perms_for(tmp_path, allow_paths=[], allow_commands=[])
        path_args = {"path": str(tmp_path / "f.txt")}
        first = execute_tool("read_file", path_args, perms)
        second = execute_tool("read_file", path_args, perms)
        assert first.output == second.output
        cmd_args = {"command": "echo hi"}
        first_cmd = execute_tool("run_command", cmd_args, perms)
        second_cmd = execute_tool("run_command", cmd_args, perms)
        assert first_cmd.output == second_cmd.output


# ---------------------------------------------------------------------------
# Integration seam with E1.2 (public surfaces only)
# ---------------------------------------------------------------------------


class TestIntegrationSeam:
    def test_parsed_tool_call_request_executes_for_each_tool(self, tmp_path):
        """A ToolCallRequest from parse_tool_call, validated against
        tool_definitions(permissions), executes through execute_tool."""
        root = tmp_path / "root"
        root.mkdir()
        f = root / "note.txt"
        f.write_text("draft\n")
        perms = perms_for(
            tmp_path,
            enabled=["read_file", "write_file", "edit_file", "list_dir", "run_command"],
        )
        tools = tool_definitions(perms)
        assert [t["function"]["name"] for t in tools] == [
            "read_file",
            "write_file",
            "edit_file",
            "list_dir",
            "run_command",
        ]
        calls = [
            ("read_file", {"path": str(f)}),
            ("write_file", {"path": str(f), "content": "draft\nmore\n"}),
            ("edit_file", {"path": str(f), "old": "draft", "new": "final"}),
            ("list_dir", {"path": str(root)}),
            ("run_command", {"command": "echo done"}),
        ]
        for name, arguments in calls:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": name, "arguments": arguments}}
                ],
            }
            parsed = parse_tool_call(message, tools)
            assert isinstance(parsed, ToolCallRequest)
            result = execute_tool(parsed.name, parsed.arguments, perms)
            assert result.ok, result.output
        assert f.read_text() == "final\nmore\n"

    def test_section_9_proof_scenario_on_temp_fixture(self, tmp_path):
        """The §9 proof seam: read a file → edit one line → run a test that
        checks the edit, as three sequential execute_tool calls."""
        fixture = tmp_path / "app.py"
        fixture.write_text("VALUE = 41\n")
        check = (
            f"python3 -c \"import re; s = open('{fixture}').read(); "
            f"import sys; sys.exit(0 if 'VALUE = 42' in s else 1)\""
        )
        perms = perms_for(tmp_path)

        read = execute_tool("read_file", {"path": str(fixture)}, perms)
        assert read.ok
        assert "VALUE = 41" in read.output

        edit = execute_tool(
            "edit_file",
            {"path": str(fixture), "old": "VALUE = 41", "new": "VALUE = 42"},
            perms,
        )
        assert edit.ok

        test_run = execute_tool("run_command", {"command": check}, perms)
        assert test_run.ok
        assert "exit_code: 0" in test_run.output
