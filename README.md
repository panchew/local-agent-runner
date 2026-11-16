# Local Agent Runner

**v2.0.0 — Phase P2 (First Real Run) delivered.** The engine now carries the full CONTRACT.md
§4 coding toolset and permission model, exposes the adapter-facing `--context` flag CONTRACT §7
requires, and has proven itself against a real Epic: [ai-project-system](../ai-project-system)
built the `bin/run-dev-agent` adapter, wired a real tool-calling model, and ran one live,
non-mocked Epic through its orchestrator with this runner as `dev_command` — converging on
attempt 1 of 3.

**Unreleased, on top of v2.0.0 (Phase P3, CF-2):** pluggable custom tools for the library API
(`run(..., custom_tools=[...])`, CONTRACT §4.1), with examples and a tracked verification of a
tool that calls an external service. See `docs/phases/P3__Library_Surface/`. Offline test suite:
**275 passed** (the console-script test skips when the package isn't installed on `PATH`).

A standalone engine that runs a **tool-calling loop** with a local (ollama) model: give it a
task, a set of tools, and a model, and it drives the model → tool → result loop until the model
returns a final answer — with a full transcript of every step.

It is deliberately **general-purpose and governance-agnostic.** It now powers unattended Epic
execution in the [AI Project System](../ai-project-system) via a thin `bin/run-dev-agent`
adapter, but it works for any local-model tool-use task, coding or not — the same pattern as a
ComfyUI endpoint: a standalone local engine that callers consume.

## Start here

**[CONTRACT.md](CONTRACT.md) is the authoritative design — read it first.** This README is just
orientation.

## What v2.0.0 delivers (Phase P2, on top of v1.0.0)

- **The full coding toolset** — `write_file`, `list_dir`, and `git` join the P1 proof tools;
  `allow_paths` enforcement is now uniform across every file tool, and `git` is scoped via
  `allow_subcommands` (CONTRACT §4)
- **The `--context` CLI flag** — the last piece of the CONTRACT §7 adapter surface; seeds
  scoped reference material as a system-role message ahead of the task, exactly what
  `bin/run-dev-agent` sends (CONTRACT §2, §7)
- **The SN-3 final-answer repair nudge** — one bounded corrective round when the terminating
  turn is unusable, never breaking §5's deterministic termination — and proven load-bearing:
  the first real run's own `final_answer` was a boilerplate refusal on its converging attempt,
  correctly ignored in favor of the QA `validation_command` exit code (CONTRACT §5, SN-3)
- **The first real agentic run** — a live Epic executed through ai-project-system's
  orchestrator, this runner as `dev_command`, non-mocked, accepted in its own parent Milestone
  Chat: the project Brief's success criterion (`docs/phases/P2__First_Real_Run/`)

Carried unchanged from v1.0.0: the Ollama HTTP client, the native/content tool-call parser
with schema coercion, the execution loop's repair-don't-crash semantics, and the §3
transcript/CLI exit-code contract.

Not yet built (later phases): broader hardening (multi-model validation, retry/backoff,
concurrency, packaging), any UI.

## Custom tools (library API)

The CLI exposes only the vetted built-ins (CONTRACT §4). Library callers can register their own
in-process tools. These are plain typed Python functions, and they run in the same loop with the
same parsing, type coercion, and repair-on-error behavior:

```python
from local_agent_runner import ToolPermissions, custom_tool, run

@custom_tool
def hello_world(name: str) -> str:
    """Return a greeting for someone. Pass 'name' as the person to greet."""
    return f"Hello, {name}!"

result = run("qwen2.5-coder:14b", "Greet Ada.", ToolPermissions(), custom_tools=[hello_world])
```

The schema comes from the signature (`str`/`int`/`float`/`bool`; parameters without defaults
are required) and the description from the docstring. Override either with
`@custom_tool(name=..., description=..., parameters=...)`. Handlers return a `str`, a
`ToolResult`, or any JSON-encodable value. Exceptions are fed back to the model rather than
raised. Custom tools are enabled by passing them to `run()`. `ToolPermissions` does not apply to
them, so a handler runs with the caller's privileges. A custom tool can't reuse a built-in's
name.

Several custom tools can be registered together, even when they share argument names. Calls are
routed by tool name, and there's no global registry: a tool is offered only if it's passed to
`run()`.

Working examples in `examples/`, each runnable against a live Ollama:

- `hello_world_tool.py`: one custom tool (`python examples/hello_world_tool.py --model qwen2.5-coder:14b`)
- `goodbye_world_tool.py` and `multi_tool_proof.py`: a second, independent tool, plus a proof that
  both work in one run (`python examples/multi_tool_proof.py --model qwen2.5-coder:14b`)
- `ticket_service/`: a custom tool that calls an **external service**. It includes
  `create_ticket`/`get_ticket` (`ticket_tools.py`), a fake third-party API with fault injection
  (`fake_service.py`) and a live-model proof (`live_proof.py`). The module docstring of
  `ticket_tools.py` describes the patterns to copy: credentials kept out of the model's reach,
  a pinned host, idempotency keys, and signed and verified responses.

### Verifying a custom tool that calls an external service

```bash
proof/run-custom-tool-verification.sh          # offline: tracked checks + mutation check
LIVE=1 proof/run-custom-tool-verification.sh   # also run the live-model proof (needs Ollama)
```

The script runs the tracked security, idempotency and integrity checks in
`tests/test_ticket_service_tool.py`. Then a mutation check disables each protection in the tool,
one at a time, and confirms the checks catch it. Results are written to
`proof/artifacts/custom-tools/ticket-service/`:

- `verification-results.md` / `.json`: each check's claim, outcome and recorded evidence
- `mutation-results.md` / `.json`: which checks catch which disabled protection
- `history.jsonl`: one line per run (time, commit, verdict), for tracking over time
- `live-proof.json` (with `LIVE=1`): the real-model run and its state checks

A plain `pytest` runs the same checks but writes nothing.

## Settled decisions (CONTRACT §10)

- **Both tool models:** built-in vetted tool library (CLI) + pluggable handlers (library API).
- **Default model:** `qwen2.5-coder:14b`.
- **Always containerized**, even standalone; the permission layer is a second line of defense.
- **Own repo:** this project stands alone.

## Verified host facts the design is built on

- ollama runs as a **Docker container on `http://localhost:11434`** — talk to `/api/chat`, never the CLI.
- Tool calls come back **two ways**: native `message.tool_calls` (llama3.1) **or** a JSON call in
  `message.content` (qwen coders). Read the native field first, else parse the content, then
  coerce argument types (numbers can arrive as strings).
- Hardware: RTX 5060 Ti 16 GB (shared with ComfyUI), Ryzen 5 9600X, 32 GB RAM.

## Layout

```
local_agent_runner/
  loop.py            # the model → tool → result loop          (CONTRACT §5)
  tool_calls.py      # native-first / content-fallback parsing (CONTRACT §1.2, §5)
  ollama_client.py   # ollama /api/chat HTTP client            (CONTRACT §1.1)
  tools.py           # full coding toolset + permission checks (CONTRACT §4)
  custom_tools.py    # @custom_tool: pluggable in-process handlers (CONTRACT §2, §10.1)
  cli.py             # CLI entry point                         (CONTRACT §2)
examples/            # custom tool examples (hello_world, goodbye_world, ticket_service) + live proofs
proof/               # §9 proof harness, fixture task, committed transcripts
tests/               # fully offline suite (recorded fixtures; no server/GPU)
CONTRACT.md
```

## Running the tests

The suite is fully offline — no Ollama server, no Docker, no GPU:

```bash
pip install -e ".[dev]"
pytest
```

## Reproducing the §9 proof (CONTRACT §9)

Requires the Ollama container serving `qwen2.5-coder:14b` on `http://localhost:11434` and a
free GPU (one heavy consumer at a time — pause ComfyUI first):

```bash
proof/run-proof.sh
```

The harness resets the workspace, runs the containerized 3-step task, and mechanically checks
the transcript for convergence and cleanliness. The accepted runs live in `proof/artifacts/`.
