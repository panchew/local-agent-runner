"""Unit tests for local_agent_runner.ollama_client — fully offline.

All Ollama traffic is mocked; recorded fixtures in tests/fixtures/ mirror the
real /api/chat non-streaming wire shape for both §1.2 delivery modes.
"""

import json
from pathlib import Path
from unittest import mock

import pytest
import requests

from local_agent_runner.ollama_client import (
    DEFAULT_ENDPOINT,
    DEFAULT_TIMEOUT,
    ChatMessage,
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelMissingError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def patched_post(payload, status_code=200):
    return mock.patch(
        "local_agent_runner.ollama_client.requests.post",
        return_value=FakeResponse(payload, status_code),
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]


class TestRequestShape:
    def test_chat_sends_model_messages_tools_and_stream_false(self):
        client = OllamaClient()
        messages = [ChatMessage(role="user", content="read src/app.py")]
        with patched_post(load_fixture("chat_native_tool_calls.json")) as post:
            client.chat("llama3.1:8b", messages, tools=TOOLS)

        (url,), kwargs = post.call_args
        assert url == f"{DEFAULT_ENDPOINT}/api/chat"
        body = kwargs["json"]
        assert body["model"] == "llama3.1:8b"
        assert body["messages"] == [{"role": "user", "content": "read src/app.py"}]
        assert body["tools"] == TOOLS
        assert body["stream"] is False
        assert kwargs["timeout"] == DEFAULT_TIMEOUT

    def test_endpoint_and_timeout_are_configurable(self):
        client = OllamaClient(endpoint="http://ollama.internal:9999/", timeout=42.5)
        with patched_post(load_fixture("chat_final_answer.json")) as post:
            client.chat("qwen2.5-coder:14b", [{"role": "user", "content": "hi"}])

        (url,), kwargs = post.call_args
        assert url == "http://ollama.internal:9999/api/chat"
        assert kwargs["timeout"] == 42.5

    def test_options_and_plain_dict_messages_pass_through(self):
        client = OllamaClient()
        options = {"temperature": 0.1, "num_ctx": 8192}
        with patched_post(load_fixture("chat_final_answer.json")) as post:
            client.chat(
                "qwen2.5-coder:14b",
                [{"role": "user", "content": "hi"}],
                options=options,
            )

        body = post.call_args.kwargs["json"]
        assert body["options"] == options
        assert "tools" not in body  # omitted when not given

    def test_tool_calls_survive_message_roundtrip(self):
        call = [{"function": {"name": "read_file", "arguments": {"path": "x"}}}]
        msg = ChatMessage(role="assistant", content="", tool_calls=call)
        assert msg.to_dict() == {"role": "assistant", "content": "", "tool_calls": call}
        assert ChatMessage(role="user", content="hi").to_dict() == {
            "role": "user",
            "content": "hi",
        }


class TestDeliveryModePassthrough:
    def test_native_tool_calls_pass_through_verbatim(self):
        fixture = load_fixture("chat_native_tool_calls.json")
        client = OllamaClient()
        with patched_post(fixture):
            resp = client.chat("llama3.1:8b", [], tools=TOOLS)

        assert resp.message.role == "assistant"
        assert resp.message.content == ""
        # untouched — including the string-typed "8" (§1.3 coercion is E1.2)
        assert resp.message.tool_calls == fixture["message"]["tool_calls"]
        assert resp.raw == fixture

    def test_content_embedded_tool_call_passes_through_verbatim(self):
        fixture = load_fixture("chat_content_embedded_tool_call.json")
        client = OllamaClient()
        with patched_post(fixture):
            resp = client.chat("qwen2.5-coder:7b", [], tools=TOOLS)

        # the JSON blob stays in content — no extraction (E1.2's job)
        assert resp.message.content == fixture["message"]["content"]
        assert resp.message.tool_calls == []
        assert resp.raw == fixture

    def test_plain_final_answer(self):
        fixture = load_fixture("chat_final_answer.json")
        client = OllamaClient()
        with patched_post(fixture):
            resp = client.chat("qwen2.5-coder:14b", [])

        assert resp.message.content == "The edit is complete and the test passes."
        assert resp.message.tool_calls is None  # field absent on the wire


class TestTokenCounts:
    def test_token_counts_surfaced_when_present(self):
        client = OllamaClient()
        with patched_post(load_fixture("chat_native_tool_calls.json")):
            resp = client.chat("llama3.1:8b", [])

        assert resp.eval_count == 28
        assert resp.prompt_eval_count == 217

    def test_absent_token_fields_default_to_none(self):
        fixture = load_fixture("chat_final_answer.json")
        del fixture["eval_count"]
        del fixture["prompt_eval_count"]
        client = OllamaClient()
        with patched_post(fixture):
            resp = client.chat("qwen2.5-coder:14b", [])

        assert resp.eval_count is None
        assert resp.prompt_eval_count is None


class TestErrors:
    def test_connection_refused_raises_connection_error(self):
        client = OllamaClient(endpoint="http://localhost:1")
        with mock.patch(
            "local_agent_runner.ollama_client.requests.post",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            with pytest.raises(OllamaConnectionError):
                client.chat("llama3.1:8b", [])

    def test_timeout_raises_connection_error(self):
        client = OllamaClient()
        with mock.patch(
            "local_agent_runner.ollama_client.requests.post",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            with pytest.raises(OllamaConnectionError):
                client.chat("llama3.1:8b", [])

    def test_model_missing_raises_model_missing_error(self):
        client = OllamaClient()
        error_body = load_fixture("error_model_missing.json")
        with patched_post(error_body, status_code=404):
            with pytest.raises(OllamaModelMissingError) as excinfo:
                client.chat("nonexistent-model:latest", [])

        assert "nonexistent-model" in str(excinfo.value)

    def test_other_http_error_raises_base_error(self):
        client = OllamaClient()
        with patched_post({"error": "internal server error"}, status_code=500):
            with pytest.raises(OllamaClientError) as excinfo:
                client.chat("llama3.1:8b", [])

        assert not isinstance(excinfo.value, OllamaConnectionError)
        assert not isinstance(excinfo.value, OllamaModelMissingError)

    def test_error_types_share_common_base(self):
        assert issubclass(OllamaConnectionError, OllamaClientError)
        assert issubclass(OllamaModelMissingError, OllamaClientError)
        # distinguishable by type alone (exit-code-4 mapping with a reason)
        assert not issubclass(OllamaConnectionError, OllamaModelMissingError)
        assert not issubclass(OllamaModelMissingError, OllamaConnectionError)
