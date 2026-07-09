# Local Agent Runner — Interface Contract (v0.1 DRAFT)

A standalone engine that runs a **tool-calling loop** with a local (ollama) model:
give it a task, a set of tools, and a model; it drives the model → tool → result loop
until the model produces a final answer, and returns that answer plus a full transcript.

It knows **nothing about governance.** The AI Project System consumes it through a thin
adapter (`bin/run-dev-agent`); any other project — coding or not, governed or not — can
consume it the same way. This is the same shape as ComfyUI: a standalone local engine that
callers consume, not a feature welded into the framework.

> **Status:** v0.1 accepted. This directory is the project's own git repo; the four §10
> decisions are settled. Next work is the §9 first-proof milestone.

---

## 1. Design invariants (verified on the host, 2026-07 — not assumptions)

These are measured facts the runner MUST honor:

1. **ollama is reached over HTTP, not the CLI.** It runs as a Docker container
   (`ollama/ollama:latest`) on `http://localhost:11434`; the `ollama` binary is not on PATH.
   The runner talks to `/api/chat` — it never shells out to `ollama`.
2. **Tool calls arrive two ways, depending on the model:**
   - `llama3.1:8b` → populated **native `message.tool_calls`** field.
   - `qwen2.5-coder:7b` / `:14b` → a **correct tool-call JSON in `message.content`**, native field empty.
   The runner reads `tool_calls` first; if empty, it **extracts the JSON call from `content`.**
3. **Arguments may be mistyped.** `llama3.1:8b` serialized integers as strings (`"8"`).
   The runner **coerces argument types against the tool's JSON schema** before executing.
4. **`llama3:8b` cannot tool-call** (returned empty) — it is not a supported model.
5. **The GPU is contended** (16 GB VRAM shared with ComfyUI; RAM often ~3 GB free). One heavy
   consumer at a time; the runner assumes it may not have the GPU to itself.

---

## 2. Primary interface — CLI (file-based I/O)

Mirrors how the P3 orchestrator invokes a `dev_command` and how `bin/ai-project-visual` works.

```
local-agent-runner \
  --model    qwen2.5-coder:14b \        # ollama model tag (default: qwen2.5-coder:14b)
  --task     task.md \                  # the instruction (or --task-text "...")
  --tools    tools.json \               # enabled tools + permissions (see §4)
  --context  context.md \               # OPTIONAL scoped reference material (token lever, §6)
  --system   system.txt \               # OPTIONAL system prompt
  --max-iterations 10 \                 # loop ceiling (default 10)
  --endpoint http://localhost:11434 \   # ollama HTTP API (default)
  --transcript out.json                 # where the full run record is written
```

**Exit codes:** `0` completed · `2` did-not-converge (max iterations) · `3` config/tool error ·
`4` runtime error (endpoint unreachable, model missing). A one-line reason on stderr.

A library entry point (`run(task, tools, model, ...) -> Result`) is a secondary interface for
callers that want to register custom in-process tool handlers.

---

## 3. Data contract

### Task (input)
| Field | Meaning |
|-------|---------|
| `model` | ollama model tag |
| `task` | the natural-language instruction |
| `tools` | which tools are enabled + their permissions (§4) |
| `context` | optional scoped reference text injected as a system/context message — **caller-scoped, never a governance dump** |
| `max_iterations` | loop ceiling |
| `options` | optional ollama params (temperature, num_ctx, …) |

### Result (output — the `--transcript` JSON)
| Field | Meaning |
|-------|---------|
| `status` | `completed` \| `max_iterations_exceeded` \| `error` |
| `final_answer` | the model's terminating text |
| `transcript` | ordered steps: each = `{ tool_call:{name,args}, tool_result, ms, eval_count }` |
| `iterations` | number of tool-call rounds |
| `tokens` | total `eval_count` across calls (token-cost visibility, §6) |
| `model`, `duration_ms` | run metadata |

---

## 4. Built-in tool library + permission model

The runner ships a **vetted tool library**; the task **enables a subset with scoped permissions**
(the caller does not inject arbitrary code in the CLI path). A local model running `run_command`
is powerful — permissions are the guardrail.

Initial built-ins (the coding set):

| Tool | Args | Permission knobs |
|------|------|------------------|
| `read_file` | `path, start_line?, end_line?` | `allow_paths` (globs) |
| `write_file` | `path, content` | `allow_paths` |
| `edit_file` | `path, old, new` | `allow_paths` |
| `list_dir` | `path` | `allow_paths` |
| `run_command` | `command` | `allow_commands` (patterns), `deny_commands`, `timeout` |
| `git` | `args` | `allow_subcommands` |

`tools.json` example:
```json
{
  "enabled": ["read_file", "write_file", "run_command"],
  "allow_paths": ["/repo/**"],
  "allow_commands": ["npm test", "npm run lint", "pytest*"],
  "timeout": 120
}
```

> **Safety note:** when invoked by the governance adapter, the runner already executes **inside
> the P3 Docker sandbox** (`run_in_sandbox`), so tool execution is contained even before these
> permissions apply. Standalone use outside the sandbox relies on the permission layer alone.

Custom/non-coding tools are registered through the library interface (§2).

---

## 5. The execution loop (behavior)

```
messages = [system?, context?, user(task)]
for i in 1..max_iterations:
    resp = POST /api/chat {model, messages, tools, stream:false}
    call = parse_tool_call(resp)            # §1.2 native-first, else extract from content
    if no call:
        return completed(final_answer = resp.content)
    args = coerce_types(call.args, tool.schema)   # §1.3
    if tool unknown / args invalid / not permitted:
        messages += tool_error(...)         # feed the error back — repair loop
        continue
    result = execute(tool, args)            # may raise → tool_error back to model
    messages += assistant(call) + tool(result)
return max_iterations_exceeded
```

- **Repair, don't crash:** malformed call, unknown tool, denied permission, or handler
  exception → append a clear error message as the tool result and let the model try again
  (bounded by `max_iterations`).
- **Deterministic termination:** a turn with no tool call is the final answer; the ceiling
  guarantees the loop halts.

### `parse_tool_call` (the crux, per §1.2)
1. If `message.tool_calls` non-empty → use the first (or queue multiple).
2. Else scan `message.content` for a tool call: a ```json fence or a bare
   `{"name": ..., "arguments": {...}}` → parse.
3. Validate `name` against enabled tools; coerce `arguments` to the schema.
4. Nothing parseable → treat as final answer (content is the answer).

---

## 6. Token discipline (a first-class requirement, not an afterthought)

The governance corpus is ~157 K tokens; AOG+PSG alone ~24 K. The runner must never carry that.

- **Context is caller-scoped.** The runner injects only what `--context` provides — the epic's
  contract, not the rulebook. No hidden governance load.
- **Report tokens.** Every run's transcript records `eval_count` per call and a total, so cost
  is visible and regressions are catchable.
- **Local = zero marginal token cost.** This engine exists so the high-volume grind runs on your
  GPU; the expensive cloud tokens stay in the planning layers.

---

## 7. The governance adapter (`bin/run-dev-agent`) — how the framework consumes it

A thin shim, and the *only* governance-aware piece:

1. The P3 orchestrator invokes `./bin/run-dev-agent` as the `dev_command`, with
   `AI_PROJECT_ACTIVE_MODEL` in the env.
2. The shim builds a Task: `--task` = the epic's Definition of Done, `--context` = the **scoped**
   epic spec/starter (never full governance), `--tools` = the coding set scoped to the repo,
   `--model` = `AI_PROJECT_ACTIVE_MODEL`.
3. It invokes the runner, returns the runner's exit code to the orchestrator, and writes the
   transcript into the epic's artifacts.

The hard part lives in the engine; the adapter is small — which is why the engine is standalone
and the adapter is the Epic-shaped work inside the framework.

---

## 8. Non-goals

- The runner does **not** know about governance, phases, epics, or artifacts.
- It does **not** decide which tools exist — the caller enables them.
- It does **not** inject context the caller didn't give it.
- It is **not** a chat UI, a queue, or a daemon — one task, one loop, one result.

---

## 9. First implementation milestone (the atomic proof)

Smallest thing that proves the whole contract end-to-end, building on what we already saw
(`qwen2.5-coder:7b` emitting a clean `read_file` call):

> Give `qwen2.5-coder:14b` a 3-step task — **read** a file, **edit** one line, **run** a test that
> checks the edit — with `read_file` + `edit_file` + `run_command` enabled, and confirm the loop
> converges to a passing result with a clean transcript.

If that passes, the engine is real; everything else is more tools and hardening.

---

## 10. Decisions (settled)

1. **Tool model:** built-in vetted library for the CLI **and** pluggable handlers for the library interface — both.
2. **Default dev model:** `qwen2.5-coder:14b` (strongest coder; the content-parse path is handled by §5).
3. **Safety:** the runner **always runs in a container**, even standalone — the permission layer (§4) is a second line of defense, not the only one.
4. **Home:** its own git repo (this directory), developed as a standalone project.
