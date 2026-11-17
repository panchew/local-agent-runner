"""Custom tools that call an external (third-party) ticketing API.

``make_ticket_tools(...)`` returns two tools, ``create_ticket`` and
``get_ticket``, bound to one service. Pass them to ``run()`` like any
custom tool:

    tools = make_ticket_tools("https://tickets.example.com", api_key, signing_secret)
    result = run(model, task, ToolPermissions(), custom_tools=tools)

The model only ever supplies business arguments (title, priority, ticket id).
Everything else is fixed by the caller: host, credentials, retries and trust
decisions.

Security
  - Credentials are closed over and never appear in a tool schema, an
    argument or a tool result. Any text returned to the model is redacted of
    the API key and signing secret, even if the service echoes them.
  - The host is pinned at construction. The model can't pass a URL, and an
    unknown argument such as ``url=`` is rejected before any request is made.
  - ``ticket_id`` must match ``T-<digits>``, which blocks path traversal and
    injection. It's also percent-encoded as a second layer of defence.
  - Redirects are never followed, and proxy/netrc environment settings are
    ignored (``trust_env=False``).
  - Plain ``http://`` is refused unless the host is loopback.
  - Timeouts are bounded. Responses are capped in size and rejected, not
    truncated, when they go over.

Idempotency
  - Every create sends an ``Idempotency-Key`` derived from
    ``(run_scope, tool, canonical arguments)``. Transport retries (dropped
    connections, timeouts, 502/503/504) reuse the same key, so a request the
    service already committed is never created twice. An identical
    ``create_ticket`` call repeated by the model in the same run also
    resolves to the same ticket, reported as ``"replayed": true``.
  - The scope is per tool set: build one tool set per run. Two runs that
    create "the same" ticket do create two tickets.
  - ``get_ticket`` is a read and is naturally idempotent.

Integrity
  - Requests are HMAC-signed over method, path and body. Responses must carry
    a valid HMAC. An unsigned or altered response is rejected, and the model
    never sees its contents.
  - The returned ticket must match what was asked for (title and priority on
    create, id on get). A mismatched ticket is rejected even if it's
    validly signed.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import requests

from local_agent_runner import CustomTool, ToolResult, custom_tool

PRIORITIES = ("low", "medium", "high")
TICKET_ID = re.compile(r"T-[0-9]{1,9}")
MAX_TITLE_CHARS = 200
RETRY_STATUSES = frozenset({502, 503, 504})
REDACTED = "[REDACTED]"


class TicketServiceError(Exception):
    """A failure that is reported to the model as a tool error (after redaction)."""


def make_ticket_tools(
    base_url: str,
    api_key: str,
    signing_secret: str,
    *,
    timeout: float = 10.0,
    max_attempts: int = 3,
    backoff: float = 0.5,
    max_response_bytes: int = 64_000,
    run_scope: Optional[str] = None,
) -> List[CustomTool]:
    """Build ``[create_ticket, get_ticket]`` bound to one service and one run scope."""
    client = _Client(
        base_url, api_key, signing_secret, timeout, max_attempts, backoff, max_response_bytes
    )
    scope = run_scope or uuid.uuid4().hex
    secrets = [api_key, signing_secret]

    @custom_tool(
        description=(
            "Create a support ticket in the ticketing service. Pass 'title' (a short "
            "summary) and 'priority' (one of: low, medium, high). Returns the created "
            "ticket as JSON, including its id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short summary, max 200 chars."},
                "priority": {"type": "string", "enum": list(PRIORITIES)},
            },
            "required": ["title", "priority"],
        },
    )
    def create_ticket(title: str, priority: str) -> ToolResult:
        def call() -> str:
            _validate_title(title)
            if priority not in PRIORITIES:
                raise TicketServiceError(
                    f"priority must be one of {', '.join(PRIORITIES)}; got {priority!r}"
                )
            body = {"title": title, "priority": priority}
            key = _idempotency_key(scope, "create_ticket", body)
            data, replayed = client.request("POST", "/v1/tickets", body, idempotency_key=key)
            ticket = _ticket_from(data)
            if ticket.get("title") != title or ticket.get("priority") != priority:
                raise TicketServiceError(
                    "integrity check failed: the service returned a ticket that does "
                    "not match the request; result discarded"
                )
            return json.dumps({"ticket": ticket, "replayed": replayed}, ensure_ascii=False)

        return _guarded("create_ticket", call, secrets)

    @custom_tool(
        description=(
            "Fetch an existing ticket by id from the ticketing service. Pass "
            "'ticket_id' like 'T-12'. Returns the ticket as JSON."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Ticket id, e.g. 'T-12'."}
            },
            "required": ["ticket_id"],
        },
    )
    def get_ticket(ticket_id: str) -> ToolResult:
        def call() -> str:
            if not isinstance(ticket_id, str) or not TICKET_ID.fullmatch(ticket_id):
                raise TicketServiceError(
                    f"invalid ticket_id {ticket_id!r}: expected the form T-<digits>, e.g. T-12"
                )
            data, _ = client.request("GET", "/v1/tickets/" + quote(ticket_id, safe=""))
            ticket = _ticket_from(data)
            if ticket.get("id") != ticket_id:
                raise TicketServiceError(
                    "integrity check failed: the service returned a different ticket "
                    "than requested; result discarded"
                )
            return json.dumps({"ticket": ticket}, ensure_ascii=False)

        return _guarded("get_ticket", call, secrets)

    return [create_ticket, get_ticket]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def redact(text: str, secrets: List[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


def _guarded(tool: str, call: Any, secrets: List[str]) -> ToolResult:
    """Run ``call`` and make sure every outcome is redacted before it reaches the model."""
    try:
        return ToolResult(ok=True, output=redact(call(), secrets))
    except TicketServiceError as exc:
        return ToolResult(ok=False, output=redact(f"{tool}: {exc}", secrets))
    except Exception as exc:  # noqa: BLE001 — never leak a raw traceback/secret
        return ToolResult(
            ok=False, output=redact(f"{tool}: unexpected {type(exc).__name__}: {exc}", secrets)
        )


def _validate_title(title: Any) -> None:
    if not isinstance(title, str) or not title.strip():
        raise TicketServiceError("title must be a non-empty string")
    if len(title) > MAX_TITLE_CHARS:
        raise TicketServiceError(f"title must be at most {MAX_TITLE_CHARS} characters")
    if any(ord(ch) < 32 for ch in title):
        raise TicketServiceError("title must not contain control characters or newlines")


def _canonical(body: Dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _idempotency_key(scope: str, tool: str, body: Dict[str, Any]) -> str:
    material = scope.encode() + b"\x00" + tool.encode() + b"\x00" + _canonical(body)
    return hashlib.sha256(material).hexdigest()


def _ticket_from(data: Any) -> Dict[str, Any]:
    ticket = data.get("ticket") if isinstance(data, dict) else None
    if not isinstance(ticket, dict) or not TICKET_ID.fullmatch(str(ticket.get("id", ""))):
        raise TicketServiceError("malformed response from service: no valid ticket")
    return ticket


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _Client:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        signing_secret: str,
        timeout: float,
        max_attempts: int,
        backoff: float,
        max_response_bytes: int,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise ValueError(f"base_url must be an http(s) URL, got {base_url!r}")
        if parts.scheme == "http" and not _is_loopback(parts.hostname):
            raise ValueError("refusing plain http:// to a non-loopback host; use https://")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("base_url must not contain credentials, a query or a fragment")
        if not api_key or not signing_secret:
            raise ValueError("api_key and signing_secret are required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.base_url = base_url.rstrip("/")
        self.base_path = parts.path.rstrip("/")
        self.api_key = api_key
        self.signing_secret = signing_secret
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.max_response_bytes = max_response_bytes
        self.session = requests.Session()
        self.session.trust_env = False  # no proxy/netrc env influence

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Any, bool]:
        raw = _canonical(body) if body is not None else b""
        signed_path = self.base_path + path
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Signature": _sign(self.signing_secret, method.encode() + b"\n"
                                 + signed_path.encode() + b"\n" + raw),
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(1, self.max_attempts + 1):
            last = attempt == self.max_attempts
            try:
                with self.session.request(
                    method,
                    self.base_url + path,
                    data=raw or None,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                ) as resp:
                    if resp.status_code in RETRY_STATUSES and not last:
                        self._sleep(attempt)
                        continue
                    content = self._read_capped(resp)
                    return self._verify(resp, content)
            except (requests.ConnectionError, requests.Timeout,
                    requests.exceptions.ChunkedEncodingError) as exc:
                if last:
                    raise TicketServiceError(
                        f"service unreachable after {self.max_attempts} attempt(s) "
                        f"({type(exc).__name__})"
                    ) from None
                self._sleep(attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def _sleep(self, attempt: int) -> None:
        if self.backoff:
            time.sleep(self.backoff * (2 ** (attempt - 1)))

    def _read_capped(self, resp: requests.Response) -> bytes:
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > self.max_response_bytes:
            raise TicketServiceError(
                f"response too large ({declared} bytes > {self.max_response_bytes}); rejected"
            )
        chunks, size = [], 0
        for chunk in resp.iter_content(16_384):
            size += len(chunk)
            if size > self.max_response_bytes:
                raise TicketServiceError(
                    f"response exceeded {self.max_response_bytes} bytes; rejected"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _verify(self, resp: requests.Response, content: bytes) -> Tuple[Any, bool]:
        if 300 <= resp.status_code < 400:
            raise TicketServiceError(
                f"service answered with a redirect (HTTP {resp.status_code}); "
                "redirects are not followed"
            )
        signature = resp.headers.get("X-Signature", "")
        if not hmac.compare_digest(signature, _sign(self.signing_secret, content)):
            raise TicketServiceError(
                "integrity check failed: response signature missing or invalid; "
                "result discarded"
            )
        try:
            data = json.loads(content)
        except ValueError:
            raise TicketServiceError("malformed response from service: not JSON") from None
        if resp.status_code >= 400:
            detail = data.get("error") if isinstance(data, dict) else None
            # Redact *before* truncating: a cut could otherwise leave a partial
            # secret that whole-string redaction no longer matches.
            detail = redact(str(detail), [self.api_key, self.signing_secret])
            raise TicketServiceError(
                f"service returned HTTP {resp.status_code}: {detail[:200]}"
            )
        return data, resp.headers.get("Idempotent-Replayed") == "true"


def _sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
