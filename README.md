# Local Agent Runner

**v1.0.0 — Phase P1 (Core Loop Proof) delivered.** The CONTRACT.md §9 atomic proof passed:
`qwen2.5-coder:14b` converged a read → edit → run-test task in three consecutive containerized
runs with clean transcripts. Offline test suite: **155 passed, 1 environment-conditional skip.**

A standalone engine that runs a **tool-calling loop** with a local (ollama) model: give it a
task, a set of tools, and a model, and it drives the model → tool → result loop until the model
returns a final answer — with a full transcript of every step.

It is deliberately **general-purpose and governance-agnostic.** It will power unattended Epic
execution in the [AI Project System](../ai-project-system) via a thin `bin/run-dev-agent`
adapter (a later phase), but it works for any local-model tool-use task, coding or not — the
same pattern as a ComfyUI endpoint: a standalone local engine that callers consume.

## Start here

**[CONTRACT.md](CONTRACT.md) is the authoritative design — read it first.** This README is just
orientation.

## What v1.0.0 delivers (Phase P1)

- **Ollama HTTP client** — `POST /api/chat` (`stream: false`) on a configurable endpoint
  (default `http://localhost:11434`); never shells out to an `ollama` CLI (CONTRACT §1.1)
- **Tool-call parser** — native `message.tool_calls` first, else extraction of a tool-call
  JSON from `message.content` (fenced or bare object), with argument type coercion against
  the tool's JSON schema (CONTRACT §1.2–1.3, §5)
- **Three proof tools** — `read_file`, `edit_file`, `run_command`, permission-scoped via
  `allow_paths`, `allow_commands`/`deny_commands`, and `timeout` (CONTRACT §4)
- **The execution loop** — repair-don't-crash error feedback, deterministic termination
  (no-tool-call turn = final answer; `max_iterations` ceiling), §3 Result transcript with
  per-call `eval_count` and total token accounting (CONTRACT §5–6)
- **CLI** — `local-agent-runner --model … --task … --tools … --transcript …`; exit codes
  `0` completed · `2` did-not-converge · `3` config/tool error · `4` runtime error
  (CONTRACT §2)
- **The §9 proof** — fixture task, containerized harness, and three committed converging
  transcripts (`proof/artifacts/`), 3 iterations and 134–432 tokens per run

Not yet built (later phases): `write_file`/`list_dir`/`git` tools, the library entry point
with pluggable handlers, the governance adapter, hardening, any UI.

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
  tools.py           # proof tools + permission checks         (CONTRACT §4)
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
