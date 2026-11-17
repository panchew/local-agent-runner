"""Verification of a custom tool that calls an external service.

The ``create_ticket`` / ``get_ticket`` tools (examples/ticket_service/) are
driven through the real ``run()`` loop by a scripted model. They talk over
real HTTP to a fake third-party service on localhost, with faults injected.

Every test is a tracked check (``@pytest.mark.verification``) and records its
evidence. Run ``proof/run-custom-tool-verification.sh`` to write the report.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "examples" / "ticket_service"))

from fake_service import (  # noqa: E402
    DROP_AFTER_COMMIT,
    HANG_AFTER_COMMIT,
    HUGE_RESPONSE,
    HUGE_UNDECLARED,
    INJECTION_PAYLOAD,
    LEAKY_ERROR,
    REDIRECT,
    TAMPER_RESPONSE,
    UNAVAILABLE,
    UNSIGNED_RESPONSE,
    WRONG_ECHO,
    FakeTicketService,
    RecordingServer,
    request_signing_payload,
    sign,
)
from ticket_tools import make_ticket_tools  # noqa: E402

from local_agent_runner import STATUS_COMPLETED, ToolPermissions, run  # noqa: E402
from local_agent_runner.ollama_client import ChatMessage, ChatResponse  # noqa: E402

API_KEY = "sk-test-4f9c2a7e1b8d6053a9e4"
SIGNING_SECRET = "whsec-7d1e9b3c5a2f8064d1c7"

security = lambda check_id: pytest.mark.verification(check_id, "security")  # noqa: E731
idempotency = lambda check_id: pytest.mark.verification(check_id, "idempotency")  # noqa: E731
integrity = lambda check_id: pytest.mark.verification(check_id, "integrity")  # noqa: E731


# ---------------------------------------------------------------------------
# Harness: fake service, scripted model, helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    with FakeTicketService(API_KEY, SIGNING_SECRET, hang_seconds=2.0) as svc:
        yield svc


def tools_for(svc, **overrides):
    options = dict(timeout=2.0, max_attempts=3, backoff=0, run_scope=None)
    options.update(overrides)
    api_key = options.pop("api_key", API_KEY)
    return make_ticket_tools(svc.base_url, api_key, SIGNING_SECRET, **options)


def _response(message):
    return ChatResponse(
        message=ChatMessage.from_dict(message), eval_count=1, prompt_eval_count=None, raw={}
    )


def call(name, **arguments):
    """A native tool call from the scripted model."""
    return _response(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    )


def content_call(name, **arguments):
    """A qwen-style tool call embedded in content."""
    blob = json.dumps({"name": name, "arguments": arguments})
    return _response({"role": "assistant", "content": f"```json\n{blob}\n```"})


def final(text="done"):
    return _response({"role": "assistant", "content": text})


class ScriptedModel:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, model, messages, tools=None, options=None):
        self.calls.append(
            {
                "tools": tools,
                "messages": [m.to_dict() if isinstance(m, ChatMessage) else m for m in messages],
            }
        )
        return self.script.pop(0)


def run_scripted(script, tools, permissions=None):
    model = ScriptedModel(script)
    result = run(
        "scripted-model", "Work with the ticketing service.",
        permissions or ToolPermissions(), client=model, custom_tools=tools,
    )
    return model, result


def results_of(result):
    return [step["tool_result"] for step in result.transcript]


def ticket_in(tool_result):
    return json.loads(tool_result)["ticket"]


def model_facing_text(model, result):
    """Everything the model was sent, plus the full Result the caller stores."""
    return json.dumps(model.calls, ensure_ascii=False) + json.dumps(
        result.to_dict(), ensure_ascii=False
    )


def secret_fragments(text, length=8):
    """How many distinct 8-char windows of either secret occur in ``text``.
    Catches partial leaks (e.g. a truncated key), not just whole ones."""
    found = set()
    for secret in (API_KEY, SIGNING_SECRET):
        for i in range(len(secret) - length + 1):
            if secret[i : i + length] in text:
                found.add(secret[i : i + length])
    return len(found)


def signed_request(svc, method, path, body=b"", *, key=None, signature=None, auth=API_KEY):
    """Call the fake service directly (contract tests), signing like a client."""
    headers = {
        "Authorization": f"Bearer {auth}",
        "X-Signature": signature
        or sign(SIGNING_SECRET, request_signing_payload(method, path, body)),
        "Content-Type": "application/json",
    }
    if key:
        headers["Idempotency-Key"] = key
    return requests.request(method, svc.base_url + path, data=body or None, headers=headers,
                            timeout=5)


# ===========================================================================
# Security
# ===========================================================================


@security("SEC-01")
def test_secrets_never_reach_the_model(service, record_property):
    """API key and signing secret never appear in anything sent to the model or stored in the Result, even when the service echoes them in an error."""
    tools = tools_for(service)
    service.inject(LEAKY_ERROR)
    model, result = run_scripted(
        [call("get_ticket", ticket_id="T-1"), call("create_ticket", title="Printer jam",
                                                   priority="low"), final()],
        tools,
    )
    text = model_facing_text(model, result)
    echoed = bool(service.leaked_bodies) and API_KEY in service.leaked_bodies[0]

    record_property("service_echoed_api_key_in_error", echoed)
    record_property("api_key_offset_in_service_error", service.leaked_bodies[0].index(API_KEY))
    record_property("redaction_marker_in_error", "[REDACTED]" in results_of(result)[0])
    record_property("error_shown_to_model_tail", results_of(result)[0][-60:])
    record_property("secret_8char_fragments_in_model_facing_text", secret_fragments(text))
    record_property("secrets_in_tool_schemas", secret_fragments(json.dumps(model.calls[0]["tools"])))
    record_property("authenticated_request_succeeded", results_of(result)[1].startswith("{"))

    assert echoed, "fault not exercised: the service did not echo the key"
    assert "[REDACTED]" in results_of(result)[0]
    assert secret_fragments(text) == 0
    assert results_of(result)[1].startswith("{")  # the key did work on the wire


@security("SEC-02")
def test_model_cannot_choose_the_host(service, record_property):
    """Extra URL/host arguments from the model are rejected before any request; the pinned host is the only one contacted."""
    with RecordingServer() as attacker:
        model, result = run_scripted(
            [
                call("create_ticket", title="x", priority="low", url=attacker.url),
                call("create_ticket", title="x", priority="low", base_url=attacker.url),
                call("get_ticket", ticket_id="T-1", endpoint=attacker.url),
                final(),
            ],
            tools_for(service),
        )
        record_property("attempts", 3)
        record_property("attacker_hits", len(attacker.hits))
        record_property("requests_reaching_service", len(service.requests_log))
        record_property("sample_feedback", results_of(result)[0])
        assert attacker.hits == []
    assert service.requests_log == []
    assert all("unexpected keyword argument" in r for r in results_of(result))


INJECTION_IDS = [
    "../admin/export",
    "T-1/../../admin",
    "T-1?admin=1",
    "%2e%2e/admin",
    "T-1#frag",
    "http://127.0.0.1:1/admin",
    "T-1\n",
    " T-1",
    "T-1 OR 1=1",
]


@security("SEC-03")
def test_ticket_id_injection_is_rejected_before_any_request(service, record_property):
    """Path-traversal / URL / injection payloads in ticket_id are rejected locally; the service (and its /admin honeypot) is never reached."""
    script = [call("get_ticket", ticket_id=p) for p in INJECTION_IDS] + [final()]
    _, result = run_scripted(script, tools_for(service))

    record_property("payloads_tried", INJECTION_IDS)
    record_property("requests_reaching_service", len(service.requests_log))
    record_property("admin_honeypot_hits", service.admin_hits)
    assert service.requests_log == [] and service.admin_hits == 0
    assert all("invalid ticket_id" in r for r in results_of(result))

    # Non-vacuous: the honeypot does register a direct hit.
    requests.get(service.base_url + "/admin/export", timeout=5)
    record_property("honeypot_is_live", service.admin_hits == 1)
    assert service.admin_hits == 1


@security("SEC-04")
def test_redirects_are_not_followed(service, record_property):
    """A redirect to another host is refused, not followed; the attacker host receives nothing (no credentials, no body)."""
    with RecordingServer() as attacker:
        service.inject(REDIRECT, arg=attacker.url + "/steal")
        _, result = run_scripted(
            [call("create_ticket", title="Laptop", priority="high"), final()], tools_for(service)
        )
        record_property("feedback", results_of(result)[0])
        record_property("attacker_hits", len(attacker.hits))
        record_property("requests_to_service", len(service.requests_log))
        assert attacker.hits == []
    assert "redirects are not followed" in results_of(result)[0]
    assert len(service.requests_log) == 1  # a redirect is not retried either


@security("SEC-05")
def test_insecure_base_urls_are_refused(record_property):
    """Plain http:// to a non-loopback host, or URLs carrying credentials/query, are refused when the tools are built."""
    refused, accepted = {}, {}
    for url in ["http://tickets.example.com", "https://user:pw@tickets.example.com",
                "https://tickets.example.com?k=v", "ftp://tickets.example.com"]:
        with pytest.raises(ValueError) as exc:
            make_ticket_tools(url, API_KEY, SIGNING_SECRET)
        refused[url] = str(exc.value)
    for url in ["https://tickets.example.com", "https://tickets.example.com/api",
                "http://127.0.0.1:8080", "http://localhost:8080"]:
        make_ticket_tools(url, API_KEY, SIGNING_SECRET)
        accepted[url] = "ok"
    record_property("refused", refused)
    record_property("accepted", list(accepted))


@security("SEC-06")
@pytest.mark.parametrize(
    "permissions",
    [
        ToolPermissions(),
        ToolPermissions(enabled=["run_command"], allow_commands=["pytest*"]),
    ],
    ids=["no-builtins", "run_command-scoped"],
)
def test_prompt_injection_in_service_data_cannot_escalate(service, tmp_path, permissions,
                                                          record_property):
    """Injected instructions in third-party data reach the model as data, but a model that obeys them is stopped by the permission layer: no command runs."""
    sentinel = tmp_path / "pwned"
    ticket_id = service.seed_ticket(INJECTION_PAYLOAD.format(sentinel=sentinel))
    _, result = run_scripted(
        [
            call("get_ticket", ticket_id=ticket_id),
            call("run_command", command=f"touch {sentinel}"),  # the model "obeys"
            final(),
        ],
        tools_for(service),
        permissions,
    )
    delivered, blocked = results_of(result)
    record_property("injection_delivered_as_data", "IGNORE ALL PREVIOUS" in delivered)
    record_property("escalation_feedback", blocked)
    record_property("command_executed", sentinel.exists())
    assert "IGNORE ALL PREVIOUS" in delivered
    assert not sentinel.exists()
    assert ("unknown tool" in blocked) or ("is denied" in blocked)


@security("SEC-07")
def test_wrong_credentials_fail_cleanly(service, record_property):
    """With a wrong API key the call fails with a clear 401, nothing is created, and the wrong key is not echoed back."""
    wrong = "sk-test-WRONGWRONGWRONGWRONG"
    tools = tools_for(service, api_key=wrong)
    model, result = run_scripted([call("create_ticket", title="x", priority="low"), final()], tools)
    record_property("feedback", results_of(result)[0])
    record_property("tickets_on_server", len(service.tickets))
    record_property("wrong_key_in_model_text", wrong in model_facing_text(model, result))
    assert "HTTP 401" in results_of(result)[0]
    assert service.tickets == {}
    assert wrong not in model_facing_text(model, result)


@security("SEC-08")
def test_hanging_service_is_time_bounded(service, record_property):
    """A service that never answers costs at most timeout x attempts; the model gets an error and the run still completes."""
    service.inject(HANG_AFTER_COMMIT, times=3)
    tools = tools_for(service, timeout=0.3, max_attempts=3)
    start = time.monotonic()
    _, result = run_scripted([call("create_ticket", title="Slow", priority="low"), final()], tools)
    elapsed = time.monotonic() - start
    record_property("elapsed_s", round(elapsed, 2))
    record_property("bound_s", 0.3 * 3 + 1.0)
    record_property("attempts_sent", len(service.posts()))
    record_property("feedback", results_of(result)[0])
    assert elapsed < 0.3 * 3 + 1.0
    assert len(service.posts()) == 3
    assert "unreachable after 3 attempt(s)" in results_of(result)[0]
    assert result.status == STATUS_COMPLETED


@security("SEC-09")
@pytest.mark.parametrize("fault", [HUGE_RESPONSE, HUGE_UNDECLARED],
                         ids=["declared-length", "undeclared-length"])
def test_oversized_response_is_rejected(service, fault, record_property):
    """A multi-megabyte response is rejected (not truncated, not forwarded), whether or not it declares its size up front."""
    ticket_id = service.seed_ticket("Big")
    service.inject(fault)
    model, result = run_scripted([call("get_ticket", ticket_id=ticket_id), final()],
                                 tools_for(service, max_response_bytes=64_000))
    feedback = results_of(result)[0]
    record_property("feedback", feedback)
    record_property("feedback_chars", len(feedback))
    record_property("largest_message_to_model_chars",
                    max(len(m.get("content") or "") for c in model.calls for m in c["messages"]))
    assert "rejected" in feedback and len(feedback) < 300
    assert "xxxxxxxx" not in model_facing_text(model, result)


# ===========================================================================
# Idempotency
# ===========================================================================


@idempotency("IDEM-01")
def test_repeated_identical_create_makes_one_ticket(service, record_property):
    """The model calling create_ticket twice with the same arguments creates one ticket; the second call is a replay of the first."""
    _, result = run_scripted(
        [call("create_ticket", title="VPN down", priority="high")] * 2 + [final()],
        tools_for(service),
    )
    first, second = (json.loads(r) for r in results_of(result))
    record_property("posts_sent", len(service.posts()))
    record_property("distinct_idempotency_keys", len(set(service.idempotency_keys())))
    record_property("tickets_on_server", len(service.tickets))
    record_property("second_call_replayed", second["replayed"])
    assert len(service.tickets) == 1
    assert first["ticket"] == second["ticket"]
    assert (first["replayed"], second["replayed"]) == (False, True)


@idempotency("IDEM-02")
def test_lost_response_after_commit_is_retried_safely(service, record_property):
    """If the service commits but the connection drops before the reply, the transport retry reuses the key: one ticket, correct result."""
    service.inject(DROP_AFTER_COMMIT)
    _, result = run_scripted([call("create_ticket", title="Disk full", priority="medium"),
                              final()], tools_for(service))
    out = json.loads(results_of(result)[0])
    record_property("posts_sent", len(service.posts()))
    record_property("first_attempt_status", service.posts()[0].status)
    record_property("distinct_idempotency_keys", len(set(service.idempotency_keys())))
    record_property("tickets_on_server", len(service.tickets))
    record_property("result_replayed", out["replayed"])
    assert len(service.posts()) == 2 and service.posts()[0].status is None
    assert len(set(service.idempotency_keys())) == 1
    assert len(service.tickets) == 1 and out["ticket"]["id"] == "T-1"


@idempotency("IDEM-03")
def test_timeout_after_commit_is_retried_safely(service, record_property):
    """If the service commits but replies too slowly, the timed-out request is retried with the same key: one ticket."""
    service.inject(HANG_AFTER_COMMIT)
    _, result = run_scripted([call("create_ticket", title="Slow DB", priority="low"), final()],
                             tools_for(service, timeout=0.3))
    out = json.loads(results_of(result)[0])
    record_property("posts_sent", len(service.posts()))
    record_property("distinct_idempotency_keys", len(set(service.idempotency_keys())))
    record_property("tickets_on_server", len(service.tickets))
    assert len(service.posts()) == 2 and len(service.tickets) == 1
    assert out["replayed"] is True


@idempotency("IDEM-04")
def test_transient_unavailability_is_retried(service, record_property):
    """503s before the commit are retried with the same key until success: exactly one ticket."""
    service.inject(UNAVAILABLE, times=2)
    _, result = run_scripted([call("create_ticket", title="Flaky", priority="low"), final()],
                             tools_for(service))
    record_property("posts_sent", len(service.posts()))
    record_property("statuses", [r.status for r in service.posts()])
    record_property("tickets_on_server", len(service.tickets))
    assert [r.status for r in service.posts()] == [503, 503, 201]
    assert len(service.tickets) == 1 and results_of(result)[0].startswith("{")


@idempotency("IDEM-05")
def test_retries_are_bounded_and_model_retry_is_safe(service, record_property):
    """Retries stop at max_attempts (no ticket, error to the model); when the model later retries the same call, exactly one ticket results."""
    service.inject(UNAVAILABLE, times=3)
    _, result = run_scripted(
        [call("create_ticket", title="Outage", priority="high")] * 2 + [final()],
        tools_for(service),
    )
    failed, retried = results_of(result)
    record_property("posts_sent", len(service.posts()))
    record_property("first_call_feedback", failed)
    record_property("tickets_on_server", len(service.tickets))
    assert len(service.posts()) == 4  # 3 bounded attempts + 1 for the model's retry
    assert "HTTP 503" in failed
    assert len(service.tickets) == 1 and json.loads(retried)["replayed"] is False


@idempotency("IDEM-06")
def test_model_retry_after_ambiguous_failure_does_not_duplicate(service, record_property):
    """When every attempt times out after the service committed, the tool reports failure; the model's retry then returns the already-committed ticket, not a duplicate."""
    service.inject(HANG_AFTER_COMMIT, times=3)
    _, result = run_scripted(
        [call("create_ticket", title="Ambiguous", priority="medium")] * 2 + [final()],
        tools_for(service, timeout=0.3),
    )
    failed, retried = results_of(result)
    record_property("first_call_feedback", failed)
    record_property("tickets_after_first_call_committed", True)
    record_property("tickets_on_server", len(service.tickets))
    record_property("retry_replayed", json.loads(retried)["replayed"])
    assert "unreachable" in failed
    assert len(service.tickets) == 1 and json.loads(retried)["replayed"] is True


@idempotency("IDEM-07")
def test_different_arguments_are_not_deduplicated(service, record_property):
    """Idempotency doesn't over-collapse: different titles or priorities create distinct tickets."""
    run_scripted(
        [
            call("create_ticket", title="A", priority="low"),
            call("create_ticket", title="B", priority="low"),
            call("create_ticket", title="A", priority="high"),
            final(),
        ],
        tools_for(service),
    )
    record_property("tickets_on_server", len(service.tickets))
    record_property("distinct_idempotency_keys", len(set(service.idempotency_keys())))
    assert len(service.tickets) == 3


@idempotency("IDEM-08")
def test_idempotency_scope_is_per_run(service, record_property):
    """Separate tool sets (separate runs) create separate tickets; reusing a run_scope (resuming a run) replays instead."""
    script = lambda: [call("create_ticket", title="Weekly report", priority="low"), final()]  # noqa: E731
    run_scripted(script(), tools_for(service))
    run_scripted(script(), tools_for(service))
    separate_runs = len(service.tickets)
    run_scripted(script(), tools_for(service, run_scope="run-42"))
    _, resumed = run_scripted(script(), tools_for(service, run_scope="run-42"))
    record_property("tickets_after_two_independent_runs", separate_runs)
    record_property("tickets_after_resumed_run", len(service.tickets))
    assert separate_runs == 2
    assert len(service.tickets) == 3 and json.loads(results_of(resumed)[0])["replayed"]


@idempotency("IDEM-09")
def test_reads_are_idempotent(service, record_property):
    """Repeated get_ticket calls return identical results and never change service state."""
    ticket_id = service.seed_ticket("Read me", "medium")
    before = json.dumps(service.tickets, sort_keys=True)
    _, result = run_scripted([call("get_ticket", ticket_id=ticket_id)] * 3 + [final()],
                             tools_for(service))
    record_property("identical_results", len(set(results_of(result))) == 1)
    record_property("state_unchanged", before == json.dumps(service.tickets, sort_keys=True))
    record_property("posts_sent", len(service.posts()))
    assert len(set(results_of(result))) == 1
    assert before == json.dumps(service.tickets, sort_keys=True) and service.posts() == []


@idempotency("IDEM-10")
def test_service_contract_rejects_key_reuse_with_different_body(service, record_property):
    """Contract check on the fake service itself (so the other checks are meaningful): the same key with a different body is a 409 and creates nothing."""
    first = signed_request(service, "POST", "/v1/tickets",
                           b'{"priority":"low","title":"one"}', key="k1")
    replay = signed_request(service, "POST", "/v1/tickets",
                            b'{"priority":"low","title":"one"}', key="k1")
    conflict = signed_request(service, "POST", "/v1/tickets",
                              b'{"priority":"low","title":"two"}', key="k1")
    no_key = signed_request(service, "POST", "/v1/tickets", b'{"priority":"low","title":"x"}')
    record_property("statuses", [first.status_code, replay.status_code, conflict.status_code,
                                 no_key.status_code])
    record_property("replay_header", replay.headers.get("Idempotent-Replayed"))
    record_property("tickets_on_server", len(service.tickets))
    assert (first.status_code, replay.status_code, conflict.status_code) == (201, 201, 409)
    assert no_key.status_code == 400
    assert replay.headers.get("Idempotent-Replayed") == "true" and len(service.tickets) == 1


# ===========================================================================
# Integrity
# ===========================================================================


@integrity("INT-01")
def test_requests_are_signed_and_tampering_is_rejected(service, record_property):
    """Every request the tool sends carries a valid HMAC; a request whose body was altered after signing is rejected and creates nothing."""
    run_scripted([call("create_ticket", title="Signed", priority="low"),
                  call("get_ticket", ticket_id="T-1"), final()], tools_for(service))
    all_valid = all(r.signature_valid for r in service.requests_log)
    good_sig = sign(SIGNING_SECRET, request_signing_payload(
        "POST", "/v1/tickets", b'{"priority":"low","title":"orig"}'))
    tampered = signed_request(service, "POST", "/v1/tickets",
                              b'{"priority":"high","title":"orig"}', key="t1", signature=good_sig)
    record_property("tool_requests", len(service.requests_log) - 1)
    record_property("all_tool_requests_signature_valid", all_valid)
    record_property("tampered_request_status", tampered.status_code)
    record_property("tickets_on_server", len(service.tickets))
    assert all_valid and tampered.status_code == 401 and len(service.tickets) == 1


@integrity("INT-02")
@pytest.mark.parametrize("operation", ["create", "get"])
def test_tampered_response_is_discarded(service, operation, record_property):
    """A response altered in transit is caught by the signature check specifically (not just by a later field comparison); the model never sees the altered data, and its retry gets the genuine ticket."""
    if operation == "create":
        step = call("create_ticket", title="Tamper", priority="low")
    else:  # get only checks the id, so the signature is the only guard on priority
        step = call("get_ticket", ticket_id=service.seed_ticket("Tamper", "low"))
    service.inject(TAMPER_RESPONSE)
    model, result = run_scripted([step, step, final()], tools_for(service))
    rejected, retried = results_of(result)
    record_property("feedback", rejected)
    record_property("tampered_value_seen_by_model", "TAMPERED" in model_facing_text(model, result))
    record_property("retry_ticket", ticket_in(retried))
    record_property("tickets_on_server", len(service.tickets))
    assert "response signature missing or invalid" in rejected
    assert "TAMPERED" not in model_facing_text(model, result)
    assert ticket_in(retried)["priority"] == "low" and len(service.tickets) == 1


@integrity("INT-03")
def test_unsigned_response_is_discarded(service, record_property):
    """A response with no signature is rejected even though its content is otherwise fine."""
    ticket_id = service.seed_ticket("Unsigned")
    service.inject(UNSIGNED_RESPONSE)
    _, result = run_scripted([call("get_ticket", ticket_id=ticket_id), final()],
                             tools_for(service))
    record_property("feedback", results_of(result)[0])
    assert "signature missing or invalid" in results_of(result)[0]


@integrity("INT-04")
@pytest.mark.parametrize("operation", ["create", "get"])
def test_validly_signed_but_wrong_ticket_is_discarded(service, operation, record_property):
    """A correctly signed response describing a different ticket than requested is rejected (semantic check beyond the signature)."""
    ticket_id = service.seed_ticket("Mine")
    service.inject(WRONG_ECHO)
    step = (call("create_ticket", title="Mine", priority="low") if operation == "create"
            else call("get_ticket", ticket_id=ticket_id))
    model, result = run_scripted([step, final()], tools_for(service))
    record_property("feedback", results_of(result)[0])
    record_property("foreign_data_seen_by_model",
                    "someone else" in model_facing_text(model, result))
    assert "does not match the request" in results_of(result)[0] or \
        "different ticket than requested" in results_of(result)[0]
    assert "someone else" not in model_facing_text(model, result)


FIDELITY_TITLES = [
    "Ünïcödé — naïve café 日本語",
    'Quotes "double" and \'single\' and `back`',
    "Backslash \\ and JSON-ish {\"a\": [1, 2]}",
    "Emoji 🚀🔥 and symbols <>&%$#@!",
    "x" * 200,
]


@integrity("INT-05")
def test_round_trip_fidelity(service, record_property):
    """Titles with unicode, quotes, JSON-like text and the 200-char maximum are stored and returned byte-for-byte; invalid titles are rejected before sending."""
    script = [content_call("create_ticket", title=t, priority="medium") for t in FIDELITY_TITLES]
    script += [call("create_ticket", title="x" * 201, priority="low"),
               call("create_ticket", title="line1\nline2", priority="low"),
               call("create_ticket", title="ok", priority="urgent"), final()]
    _, result = run_scripted(script, tools_for(service))
    stored = [t["title"] for t in service.tickets.values()]
    returned = [ticket_in(r)["title"] for r in results_of(result)[: len(FIDELITY_TITLES)]]
    rejected = results_of(result)[len(FIDELITY_TITLES):]
    record_property("titles_tested", len(FIDELITY_TITLES))
    record_property("stored_exactly", stored == FIDELITY_TITLES)
    record_property("returned_exactly", returned == FIDELITY_TITLES)
    record_property("rejected_locally", rejected)
    record_property("posts_sent", len(service.posts()))
    assert stored == FIDELITY_TITLES and returned == FIDELITY_TITLES
    assert len(service.posts()) == len(FIDELITY_TITLES)
    assert all(r.startswith("create_ticket:") for r in rejected)


@integrity("INT-06")
def test_end_to_end_state_reconciles_with_transcript(service, record_property, report_dir):
    """After a multi-step run with a duplicate and a dropped connection, the service's state matches the transcript exactly: same tickets, same fields, no extras."""
    service.inject(DROP_AFTER_COMMIT)
    model, result = run_scripted(
        [
            content_call("create_ticket", title="Email outage", priority="high"),
            call("create_ticket", title="New laptop", priority="low"),
            content_call("create_ticket", title="Email outage", priority="high"),  # duplicate
            call("get_ticket", ticket_id="T-2"),
            call("get_ticket", ticket_id="T-1"),
            final("Created T-1 and T-2."),
        ],
        tools_for(service),
    )
    seen = {}
    for r in results_of(result):
        ticket = ticket_in(r)
        assert seen.setdefault(ticket["id"], ticket) == ticket  # consistent across calls
    record_property("tickets_in_transcript", sorted(seen))
    record_property("tickets_on_server", sorted(service.tickets))
    record_property("server_matches_transcript", seen == service.tickets)
    record_property("secret_fragments_in_result", secret_fragments(model_facing_text(model, result)))
    assert result.status == STATUS_COMPLETED
    assert seen == service.tickets and len(service.tickets) == 2
    if report_dir is not None:  # keep the full run record as evidence
        (report_dir / "int-06-run-result.json").write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"
        )


# ---------------------------------------------------------------------------
# Harness self-test (not a tracked check): the live-proof script's own logic
# ---------------------------------------------------------------------------


def test_live_proof_script_passes_with_a_well_behaved_model(tmp_path):
    import live_proof

    model = ScriptedModel([
        content_call("create_ticket", title=live_proof.TITLE, priority="high"),
        call("get_ticket", ticket_id="T-1"),
        final("T-1, high"),
    ])
    assert live_proof.main(["--out", str(tmp_path)], client=model) == 0
    record = json.loads((tmp_path / "live-proof.json").read_text())
    assert record["verdict"] == "PASS" and all(record["checks"].values())


def test_live_proof_script_fails_when_the_model_duplicates(tmp_path):
    import live_proof

    model = ScriptedModel([
        call("create_ticket", title=live_proof.TITLE, priority="high"),
        call("create_ticket", title=live_proof.TITLE + " (again)", priority="high"),
        final("done"),
    ])
    assert live_proof.main(["--out", str(tmp_path)], client=model) == 1
    checks = json.loads((tmp_path / "live-proof.json").read_text())["checks"]
    assert checks["exactly one ticket on the service"] is False
    assert checks["model called get_ticket"] is False
