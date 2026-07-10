# Local Agent Runner

A standalone engine that runs a **tool-calling loop** with a local (ollama) model: give it a
task, a set of tools, and a model, and it drives the model → tool → result loop until the model
returns a final answer — with a full transcript of every step.

It is deliberately **general-purpose and governance-agnostic.** It will power unattended Epic
execution in the [AI Project System](../ai-project-system) via a thin `bin/run-dev-agent`
adapter, but it works for any local-model tool-use task, coding or not — the same pattern as a
ComfyUI endpoint: a standalone local engine that callers consume.

## Start here

**[CONTRACT.md](CONTRACT.md) is the authoritative design — read it first.** This README is just
orientation.

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

## Recommended stack

**Python** — matches the ai-project-system tooling (`ai-project-orchestrator`, `ai-project-visual`);
ollama HTTP + JSON + subprocess needs no heavy framework.

Suggested layout:

```
local_agent_runner/
  loop.py        # the model → tool → result loop           (CONTRACT §5)
  parse.py       # native-first / content-fallback parsing   (CONTRACT §1.2, §5)
  client.py      # ollama /api/chat HTTP client              (CONTRACT §1.1)
  tools/         # built-in vetted tools + permission checks  (CONTRACT §4)
cli.py           # CLI entry point                            (CONTRACT §2)
tests/
CONTRACT.md
```

## Running the tests

The suite is fully offline — no Ollama server, no Docker, no GPU:

```bash
pip install -e ".[dev]"
pytest
```

## First milestone — build this first (CONTRACT §9)

> Give `qwen2.5-coder:14b` a 3-step task — **read** a file, **edit** one line, **run** a test that
> checks the edit — with `read_file` + `edit_file` + `run_command` enabled, and confirm the loop
> converges to a passing result with a clean transcript.

Build the ollama client, the loop, the parser, and those three tools; make that pass. Everything
after is more tools and hardening.
