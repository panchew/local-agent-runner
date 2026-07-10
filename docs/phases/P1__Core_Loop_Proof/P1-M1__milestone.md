---
project: local-agent-runner
phase: P1
milestone: M1
type: milestone
status: completed
last_updated: 2026-07-10
---

# Milestone M1 — First-Proof Milestone

## Purpose

Build the smallest complete engine that proves the CONTRACT.md v0.1 core loop end-to-end:
an Ollama HTTP client, the model → tool → result execution loop with its repair path, the
native/content tool-call parser with schema-based argument coercion, and the three proof
tools — then converge the §9 atomic proof task (read → edit → run-test) with
`qwen2.5-coder:14b` and a clean transcript.

This milestone ensures:
- The engine's crux — `parse_tool_call` across both delivery modes (§1.2) — is real and tested
- The loop terminates deterministically and repairs instead of crashing (§5)
- The §9 proof converges reproducibly, answering the project's founding question in its
  smallest form

---

## Problem Statement

The project rests on one unresolved question: can a local model, reached over Ollama's HTTP
API, reliably drive a tool-calling loop to a correct, verifiable result? Until the §9 proof
passes, everything else in the roadmap (more tools, the governance adapter, hardening) is
speculative. M1 exists to retire that risk first, with the minimum construction necessary.

---

## Goals

By the end of this milestone, the system must:

1. Reach Ollama exclusively over HTTP (`POST /api/chat`, `stream: false`) at a configurable
   endpoint defaulting to `http://localhost:11434` — never shelling out to an `ollama` CLI
2. Parse tool calls in both observed delivery modes: populated native `message.tool_calls`
   first, else a correct tool-call JSON extracted from `message.content` (```json fence or
   bare `{"name": ..., "arguments": {...}}` object)
3. Coerce mistyped arguments against the tool's JSON schema before execution (e.g. `"8"` → 8)
4. Run the CONTRACT.md §5 execution loop with deterministic termination (a turn with no tool
   call is the final answer; `max_iterations` ceiling, default 10) and repair-don't-crash
   error feedback (malformed call, unknown tool, denied permission, or handler exception →
   error fed back as the tool result)
5. Provide the three proof tools — `read_file`, `edit_file`, `run_command` — with the §4
   permission knobs the proof requires (`allow_paths` globs; `allow_commands` /
   `deny_commands` patterns and `timeout`)
6. Emit a transcript per the §3 Result shape: `status`, `final_answer`, ordered steps
   (`tool_call`, `tool_result`, `ms`, `eval_count`), `iterations`, total `tokens`, `model`,
   `duration_ms`
7. Be invocable from a CLI sufficient for the proof (§2 flags: `--model`, `--task` /
   `--task-text`, `--tools`, `--max-iterations`, `--endpoint`, `--transcript`; exit codes
   `0` completed, `2` did-not-converge, `3` config/tool error, `4` runtime error, with a
   one-line stderr reason)
8. Converge the §9 proof task — `qwen2.5-coder:14b` reads a file, edits one line, runs a
   test that checks the edit — to a passing result with a clean transcript, reproducibly,
   running inside a container

---

## Non-Goals

This milestone explicitly does **not** aim to:

- Build the governance adapter (`bin/run-dev-agent`) or add any governance awareness to the
  engine
- Ship the remaining built-in tools (`write_file`, `list_dir`, `git`) or the full permission
  model beyond what the three proof tools need
- Expose the library entry point (`run(...) -> Result`) with pluggable custom tool handlers
- Harden the engine: multi-model validation beyond the default model, retry/backoff,
  concurrency, packaging/distribution
- Build any UI

---

## In Scope

- Ollama HTTP client for `/api/chat` (non-streaming), endpoint configurable, connection and
  model-missing failures surfaced as runtime errors (exit code 4 semantics)
- `parse_tool_call` covering native `tool_calls` and content-embedded JSON, with validation
  against enabled tools
- Argument type coercion against tool JSON schemas
- The execution loop (§5) including the repair loop and deterministic termination
- The three proof tools with minimum permission scoping (§4 knobs for these tools)
- Transcript output per the §3 Result shape, including per-call `eval_count` and totals
- CLI invocation sufficient to run the proof task; exit codes 0/2/3/4
- Unit tests for the parser, coercion, permission checks, and loop termination using
  recorded/mocked responses (no GPU required)
- The §9 proof run itself: fixture task + containerized run against `qwen2.5-coder:14b`

---

## Out of Scope

- `write_file`, `list_dir`, `git` tools; `--context` / `--system` beyond what the proof needs
- The governance adapter and any artifact/phase/epic awareness
- Library API with custom tool handlers
- Retry/backoff, concurrency, multi-model support validation, packaging
- Any UI (OpenClaw/Hermes/GooseAI direction is parked)

---

## Planned Epics

### Confirmed Epics

- [E1.1 — Ollama HTTP Client](P1-M1-E1.1__spec__ollama-http-client.md) — Typed client for
  `POST /api/chat` (`stream: false`) on a configurable endpoint; maps connection/model
  failures to runtime-error semantics; never shells out to `ollama`.
- [E1.2 — Tool-Call Parser & Argument Coercion](P1-M1-E1.2__spec__tool-call-parser-and-coercion.md) —
  `parse_tool_call` (native-first, else content extraction per §1.2/§5) plus JSON-schema
  argument type coercion (§1.3); unit-tested against recorded fixtures of both delivery modes.
- [E1.3 — Proof Tools & Permission Scoping](P1-M1-E1.3__spec__proof-tools-and-permissions.md) —
  `read_file`, `edit_file`, `run_command` with `allow_paths`, `allow_commands`/`deny_commands`,
  and `timeout` enforcement; denials return deterministic tool-error messages (repair-loop
  inputs, not crashes).
- [E1.4 — Execution Loop, Transcript & CLI](P1-M1-E1.4__spec__execution-loop-transcript-cli.md) —
  The §5 loop wiring E1.1–E1.3 together: repair-don't-crash feedback, deterministic
  termination, §3 Result/transcript emission with token accounting, §2 CLI flags and exit
  codes 0/2/3/4.
- [E1.5 — §9 Proof Run](P1-M1-E1.5__spec__section-9-proof-run.md) — The fixture task
  (read → edit → run-test), the containerized invocation against `qwen2.5-coder:14b` at
  `http://localhost:11434`, and the reproducibility check (three consecutive converging runs
  with clean transcripts, committed as artifacts).

### Deferred Epics

- None.

---

## Completion Criteria

Milestone M1 is complete when all Epics under M1 are completed and closed.

Additionally:
- The §9 proof run has converged reproducibly (see Acceptance Criteria) and its transcripts
  are committed as milestone artifacts.

---

## Acceptance Criteria

- [ ] `parse_tool_call` passes unit tests for both delivery modes: populated native
      `message.tool_calls`, and correct tool-call JSON embedded in `message.content`
- [ ] Argument coercion passes unit tests for mistyped arguments (string-encoded integers at
      minimum) validated against the tool's JSON schema
- [ ] The loop repairs on malformed call, unknown tool, denied permission, and handler
      exception — verified by unit tests — and always halts (no-tool-call turn → final
      answer; `max_iterations` → exit code 2)
- [ ] Permission scoping is enforced and unit-tested for the three proof tools
      (`allow_paths`; `allow_commands`/`deny_commands`/`timeout`)
- [ ] The CLI returns exit codes 0/2/3/4 with a one-line stderr reason, and writes a
      `--transcript` JSON matching the §3 Result shape, including per-call `eval_count` and
      total `tokens`
- [ ] The §9 proof task converges with `qwen2.5-coder:14b`: exit code 0, `status:
      "completed"`, the edit verified by the test the model runs, and a clean transcript
      (every step has a well-formed `tool_call` and `tool_result`; no unrepaired errors in
      the final iteration)
- [ ] Reproducibility: three consecutive proof runs converge (milestone-level definition of
      the phase spec's "reproducibly")
- [ ] The proof run executes inside a container (CONTRACT.md §10.3) and the codebase contains
      no invocation of an `ollama` CLI

---

## Dependencies

**Internal Dependencies:**
- E1.4 depends on E1.1, E1.2, and E1.3
- E1.5 depends on E1.4 (full engine assembled)
- E1.1–E1.3 are mutually independent and may be planned/executed in any order

**External Dependencies:**
- Ollama Docker container serving `http://localhost:11434` with `qwen2.5-coder:14b` pulled
  (E1.5 only; E1.1–E1.4 test against recorded/mocked responses)
- GPU availability: contended with ComfyUI (one heavy consumer at a time) — affects only
  E1.5 proof runs

---

## Timeline

**Target Start:** TBD
**Target Completion:** TBD
**Actual Start:** 2026-07-09
**Actual Completion:** 2026-07-10 (see [Closure Declaration](P1-M1__closure-declaration.md))

---

## Notes

- **Authoritative inputs:** CONTRACT.md v0.1 (§9 proof definition wins any conflict),
  `docs/phases/P1__phase__core-loop-proof.md`, `genesis.md` (status: complete). §10
  decisions are settled — do not reopen.
- **Milestone-level decision (2026-07-09):** the phase spec's "reproducibly" is defined for
  acceptance as three consecutive converging proof runs. Recorded here so E1.5 has a
  measurable target.
- **Stack:** Python. Default model `qwen2.5-coder:14b`.
- **Host constraints (binding):** Ollama is Docker-only over HTTP; no `ollama` CLI exists on
  the host; the runner always runs inside a container, even standalone.
