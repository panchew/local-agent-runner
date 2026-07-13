# Local Agent Runner

**v2.0.0 — Phase P2 (First Real Run) delivered.** The engine now carries the full CONTRACT.md
§4 coding toolset and permission model, exposes the adapter-facing `--context` flag CONTRACT §7
requires, and has proven itself against a real Epic: [ai-project-system](../ai-project-system)
built the `bin/run-dev-agent` adapter, wired a real tool-calling model, and ran one live,
non-mocked Epic through its orchestrator with this runner as `dev_command` — converging on
attempt 1 of 3. Offline test suite: **209 passed, 1 environment-conditional skip.**

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

Not yet built (later phases): the library entry point with pluggable handlers (CF-2, deferred),
broader hardening (multi-model validation, retry/backoff, concurrency, packaging), any UI.

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
  cli.py             # CLI entry point                         (CONTRACT §2)
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
