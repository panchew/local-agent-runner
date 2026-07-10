---
project: local-agent-runner
phase: P2
milestone: null
epic: null
type: phase
status: active
last_updated: 2026-07-10
---

# Phase P2 — First Real Run

## Purpose

Take the proven core loop (P1, `v1.0.0`) from atomic proof to real use: give the runner the
full coding toolset and permission model a real Epic needs, make it a reliable `dev_command`
for the ai-project-system orchestrator, and pass the project Brief's success criterion — a
live Epic executed through the orchestrator with this runner, accepted in its parent
Milestone Chat like any other epic.

This phase focuses on:
- The remaining built-in tools (`write_file`, `list_dir`, `git`) and the full CONTRACT §4
  permission model (CF-1)
- Runner-side support for the `bin/run-dev-agent` governance adapter (CF-3, runner side only)
- Targeted hardening: the final-answer repair nudge (CF-4 / SN-3)
- The P2 exit event: the first REAL agentic run succeeding end-to-end

---

## In Scope

- `write_file`, `list_dir`, and `git` built-in tools per CONTRACT §4 (a real epic cannot
  create files with the P1 set alone)
- The full §4 permission model: `allow_paths` globs across all file tools,
  `allow_commands`/`deny_commands`/`timeout` for `run_command`, `allow_subcommands` for `git`
- **Final-answer repair nudge (SN-3):** when the terminating turn is junk (e.g. a
  `{"name":null}` blob) or the model re-calls tools until the ceiling on Q&A-shaped tasks,
  nudge one repair round for a usable final answer — bounded, never breaking §5's
  deterministic termination
- Runner-side adapter support (CF-3): whatever the CONTRACT §7 shim needs from the runner —
  stable CLI flags, exit codes, and transcript shape — verified against the orchestrator's
  invocation pattern
- The first real agentic run: a live Epic through ai-project-system's orchestrator with this
  runner as `dev_command`, accepted per the Brief's success criterion
- Housekeeping carried from P1: fix the pytest deprecation warning
  (`tests/test_check_transcript.py::test_step` returns instead of asserts) in the first P2 epic

---

## Out of Scope

- **CF-2 — the library entry point (`run(...) -> Result`) with pluggable handlers:**
  deferred by CFO decision (Creation Chat, 2026-07-10); nothing on the first-real-run path
  requires it
- **The `bin/run-dev-agent` adapter Epic itself:** per CONTRACT §7 and SN-4 it is Epic-shaped
  work *inside ai-project-system* and is planned under that project's governance; this phase
  delivers only the runner-side support it consumes
- Broad CF-4 hardening beyond the final-answer nudge: multi-model validation, retry/backoff,
  concurrency, packaging/distribution
- Any UI (still parked)

---

## Binding Constraints (SN-3 — encode in all P2 planning)

1. **Consumers MUST NOT depend on `final_answer`.** The audit of v1.0.0 showed the
   final-answer turn is systematically unreliable on Q&A-shaped tasks with
   `qwen2.5-coder:14b`, while tool calls, transcripts, and exit codes are solid. Success
   signals for the adapter path are the exit code and the QA `validation_command` — the
   runner's contract documentation and adapter-facing interface must state this explicitly.
2. **The repair nudge is bounded.** It adds at most one corrective round inside the existing
   `max_iterations` ceiling; §5 deterministic termination is inviolable.

---

## Exit Criteria

Phase P2 is complete when all milestones under P2 are completed and closed.

Additionally:
- **The first REAL agentic run succeeds:** a live Epic executed through ai-project-system's
  orchestrator with this runner as `dev_command`, accepted in its parent Milestone Chat —
  the project Brief's success criterion (CFO-confirmed, Creation Chat 2026-07-10).

---

## Milestones

- [M2 — Real-Epic Toolset](P2__First_Real_Run/P2-M2__milestone.md) — `write_file`,
  `list_dir`, `git` + the full §4 permission model; the SN-3 final-answer repair nudge; the
  pytest warning fix.
- [M3 — Adapter Readiness & First Real Run](P2__First_Real_Run/P2-M3__milestone.md) —
  runner-side CONTRACT §7 support verified against the orchestrator's invocation pattern
  (never depending on `final_answer`), then the live Epic run through ai-project-system,
  accepted per the Brief's success criterion.

---

## Notes

- **Ratification:** P2 scope ratified by the CFO via Creation Chat steering note
  (`.ai-project/artifacts/steering-notes/2026-07-10__creation-chat__steering-note.md`),
  grounded in the external v1.0.0 audit recorded in ai-project-system
  (`local-model-epic-execution.md`, 2026-07-10, verdict: "ready to move forward").
- **Cross-repo dependency (SN-4):** M3's real run requires the adapter Epic on the
  ai-project-system side (wire runner as `dev_command`, drop the `04_epic.json` trigger,
  update that repo's `epic_dev` model from `llama3:8b` to `qwen2.5-coder:14b`). That work is
  planned in ai-project-system's governance; HQ-to-HQ coordination happens at the human
  layer. If the adapter Epic is not ready when M3 needs it, the Phase Chat escalates to HQ —
  it does not reach across repos.
- **Process rule carried from P1 (CF-5):** issue Epic Delivery Authorizations *before*
  launching Coding Agents.
- **Constraints unchanged from P1:** Ollama Docker-only over HTTP (`http://localhost:11434`);
  GPU contended with ComfyUI; the runner always runs in a container (CONTRACT §10.3); solo
  project (Francisco Guzmán: CFO, Phase Lead, Contributor).
- **Authoritative inputs:** CONTRACT.md v0.1 (§4, §5, §7), the 2026-07-10 Creation Chat
  steering note (SN-3, SN-4, decisions 1–2), and P1's Phase Closure Declaration
  (carry-forward table).
