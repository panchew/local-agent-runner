"""Typed HTTP client for Ollama's ``POST /api/chat`` endpoint (non-streaming).

The client is interpretation-free: whatever delivery mode the model uses for
tool calls (native ``message.tool_calls`` or tool-call JSON embedded in
``message.content``), the response passes through verbatim. Extracting tool
calls out of content is E1.2's job (``parse_tool_call``), not this module's.

Ollama is reached over HTTP only — never via the ``ollama`` CLI or SDK
(CONTRACT.md §1.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

import requests

DEFAULT_ENDPOINT = "http://localhost:11434"
# Model inference is slow on a contended GPU (CONTRACT.md §1.5) — be generous.
DEFAULT_TIMEOUT = 300.0


class OllamaClientError(Exception):
    """Base for all runtime errors raised by OllamaClient (CLI exit code 4)."""


class OllamaConnectionError(OllamaClientError):
    """Endpoint unreachable: connection refused, DNS failure, or timeout."""


class OllamaModelMissingError(OllamaClientError):
    """The requested model is not available on the Ollama server."""


@dataclass
class ChatMessage:
    """One chat message, usable both in request ``messages`` and as the
    response ``message``.

    ``tool_calls`` is ``None`` when the wire response omits the field; when
    present it is the raw list of tool-call dicts, passed through untouched.
    """

    role: str
    content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls is not None:
            data["tool_calls"] = self.tool_calls
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        return cls(
            role=data.get("role", ""),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls"),
        )


@dataclass
class ChatResponse:
    """Typed view over an Ollama ``/api/chat`` non-streaming response.

    ``eval_count`` / ``prompt_eval_count`` are ``None`` when Ollama omits
    them (absent ≠ measured zero); ``raw`` is the unmodified response dict
    for forward-compatibility.
    """

    message: ChatMessage
    eval_count: Optional[int]
    prompt_eval_count: Optional[int]
    raw: Dict[str, Any]


def _looks_like_model_missing(error_text: str) -> bool:
    text = error_text.lower()
    return "model" in text and ("not found" in text or "no such model" in text)


class OllamaClient:
    """Minimal typed client for ``POST {endpoint}/api/chat``, always
    ``stream: false``."""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        model: str,
        messages: Sequence[Union[ChatMessage, Dict[str, Any]]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        """Send one non-streaming chat request and return the typed response.

        ``tools`` are plain dicts in Ollama's wire format (JSON-schema
        ``function`` objects); producing them is E1.3's job.

        Raises:
            OllamaConnectionError: endpoint unreachable or request timed out.
            OllamaModelMissingError: the server reports the model is not
                available.
            OllamaClientError: any other HTTP-level failure.
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                m.to_dict() if isinstance(m, ChatMessage) else m for m in messages
            ],
            "stream": False,
        }
        if tools is not None:
            payload["tools"] = tools
        if options is not None:
            payload["options"] = options

        url = f"{self.endpoint}/api/chat"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            raise OllamaConnectionError(
                f"cannot reach Ollama at {self.endpoint}: {exc}"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise OllamaClientError(f"request to {url} failed: {exc}") from exc

        if response.status_code >= 400:
            error_text = _extract_error_text(response)
            if _looks_like_model_missing(error_text):
                raise OllamaModelMissingError(
                    f"model {model!r} not available: {error_text}"
                )
            raise OllamaClientError(
                f"Ollama returned HTTP {response.status_code}: {error_text}"
            )

        data = response.json()
        return ChatResponse(
            message=ChatMessage.from_dict(data.get("message") or {}),
            eval_count=data.get("eval_count"),
            prompt_eval_count=data.get("prompt_eval_count"),
            raw=data,
        )


def _extract_error_text(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict) and "error" in body:
        return str(body["error"])
    return response.text
