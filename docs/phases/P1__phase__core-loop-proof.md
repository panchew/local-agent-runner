---
project: local-agent-runner
phase: P1
milestone: null
epic: null
type: phase
status: completed
last_updated: 2026-07-10
---

# Phase P1 — Core Loop Proof

## Purpose

Prove the core model → tool → result loop converges end-to-end on a real task, per
CONTRACT.md §9. This phase answers the project's founding question in its smallest form:
can a local model (`qwen2.5-coder:14b`, over Ollama's HTTP API) reliably drive a
tool-calling loop to a correct, verifiable result?

This phase focuses on:
- The Ollama HTTP client (`POST /api/chat`, never the CLI)
- The model → tool → result execution loop (CONTRACT.md §5), including the repair loop
- The tool-call parser: native `message.tool_calls` first, else extraction from
  `message.content`, with argument type coercion against the tool's JSON schema
  (CONTRACT.md §1.2–1.3)
- The three proof tools: `read_file`, `edit_file`, `run_command`
- The §9 atomic proof: a 3-step read → edit → run-test task that converges to a passing
  result with a clean transcript

---

## In Scope

- Ollama HTTP client for `/api/chat` on `http://localhost:11434` (endpoint configurable)
- The execution loop with deterministic termination (`max_iterations` ceiling; a turn with
  no tool call is the final answer) and repair-don't-crash error feedback
- `parse_tool_call` covering both delivery modes: populated native `tool_calls` and
  correct tool-call JSON embedded in `content`
- Argument type coercion against tool JSON schemas
- The three proof tools (`read_file`, `edit_file`, `run_command`) with the minimum
  permission scoping the proof task requires (CONTRACT.md §4 knobs for these tools)
- Transcript output per the CONTRACT.md §3 Result shape, including per-call `eval_count`
  and totals (token discipline, CONTRACT.md §6)
- CLI invocation sufficient to run the proof task (CONTRACT.md §2 flags used by the proof;
  exit codes 0/2/3/4)
- The §9 proof run itself: `qwen2.5-coder:14b` converging the 3-step task end-to-end

---

## Out of Scope

- The governance adapter (`bin/run-dev-agent`) and any governance awareness in the engine
- The remaining built-in tools (`write_file`, `list_dir`, `git`) and the full permission
  model beyond what the proof tools need
- The library entry point (`run(...) -> Result`) with pluggable custom tool handlers
- Hardening: multi-model support validation beyond the default model, retry/backoff,
  concurrency, packaging/distribution
- Any UI (the OpenClaw/Hermes/GooseAI direction is explicitly parked, not committed)

---

## Exit Criteria

Phase P1 is complete when all milestones under P1 are completed and closed.

Additionally:
- The CONTRACT.md §9 proof task (read → edit → run-test with `qwen2.5-coder:14b`)
  converges to a passing result with a clean transcript, reproducibly.

---

## Milestones

- [M1 — First-Proof Milestone](P1__Core_Loop_Proof/P1-M1__milestone.md) — Build the Ollama
  HTTP client, the model→tool→result loop, the native/content tool-call parser, and the
  three proof tools; make the §9 read → edit → run-test task converge with a clean
  transcript.

---

## Notes

- **Ratification:** Phase 1 scope ratified by HQ Chat on 2026-07-09 from `genesis.md`
  (status: complete) and CONTRACT.md v0.1 (§9, §10 settled).
- **Constraints (from genesis.md / CONTRACT.md §1):**
  - Ollama is Docker-only on this host, reached over HTTP at `http://localhost:11434`;
    the `ollama` CLI is not available and must never be shelled out to.
  - GPU is contended (RTX 5060 Ti, 16 GB VRAM shared with ComfyUI) — one heavy consumer
    at a time; the runner may not have the GPU to itself.
  - The runner always runs inside a container, even standalone (CONTRACT.md §10.3).
  - Solo project: Francisco Guzmán holds CFO, Phase Lead, and Contributor.
- **Authoritative inputs:** `genesis.md` (project root), `CONTRACT.md` v0.1 (project root).
  Any conflict between this spec and CONTRACT.md §9 is resolved in favor of the contract's
  proof definition.
