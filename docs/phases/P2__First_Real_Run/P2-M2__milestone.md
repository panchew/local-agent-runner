---
project: local-agent-runner
phase: P2
milestone: M2
type: milestone
status: active
last_updated: 2026-07-10
---

# Milestone M2 — Real-Epic Toolset

## Purpose

Give the runner the remaining built-in tools and the full CONTRACT.md §4 permission model a
real Epic needs: `write_file` and `list_dir` to create and inspect files, `git` to commit
work, and `allow_paths`/`allow_subcommands` scoping consistent with the pattern P1 already
proved for `read_file`/`edit_file`/`run_command`. It also lands the SN-3 final-answer repair
nudge and the pytest housekeeping carried forward from P1.

This milestone ensures:
- A real Epic can create files, inspect directories, and commit via git — not just read and
  edit, as P1's proof tools allowed
- The §4 permission model is uniform across every file tool, not just the three P1 proved
- The terminating turn is nudged toward usability (bounded, non-blocking) before M3 asks the
  adapter path to lean on exit codes and `validation_command` instead of `final_answer`

---

## Problem Statement

P1 proved the loop end-to-end with three read-mostly proof tools and minimal permission
knobs. A real coding Epic needs to create new files and commit them — neither is possible
yet. Separately, the v1.0.0 audit found the final-answer turn systematically unreliable on
Q&A-shaped tasks with `qwen2.5-coder:14b`; SN-3 requires a bounded repair nudge before the
engine is asked to carry real work. Without M2, M3 has no toolset to exercise in the first
real run.

---

## Goals

By the end of this milestone, the system must:

1. Provide `write_file(path, content)`, scoped by `allow_paths` globs, consistent with the
   existing file-tool permission pattern
2. Provide `list_dir(path)`, scoped by `allow_paths` globs
3. Provide `git(args)`, scoped by `allow_subcommands`
4. Enforce `allow_paths` with identical semantics across all four file tools (`read_file`,
   `edit_file`, `write_file`, `list_dir`) per CONTRACT.md §4
5. Implement the SN-3 final-answer repair nudge: when the terminating turn is unusable (e.g.
   a `{"name":null}` blob) or the model exhausts tool-calling on a Q&A-shaped task without
   producing an answer, add at most one corrective round inside the existing
   `max_iterations` ceiling — §5 deterministic termination remains inviolable
6. Fix the pytest deprecation warning in `tests/test_check_transcript.py::test_step`
   (`return` instead of `assert`) — landed in this milestone's first epic per the Phase
   spec's direction
7. Cover all new tools and the repair nudge with unit tests against recorded/mocked
   responses (no GPU required)

---

## Non-Goals

This milestone explicitly does **not** aim to:

- Build the governance adapter (`bin/run-dev-agent`) or any adapter-facing CLI/transcript
  surface — that is M3
- Expose the library entry point (`run(...) -> Result`) with pluggable custom tool handlers
  (CF-2, deferred by CFO decision)
- Pursue broader CF-4 hardening: multi-model validation, retry/backoff, concurrency,
  packaging/distribution
- Build any UI
- Change `run_command`'s permission model — it is already complete from P1

---

## In Scope

- `write_file`, `list_dir`, `git` built-in tools per CONTRACT.md §4
- The full §4 permission model: `allow_paths` globs across all file tools;
  `allow_subcommands` for `git`
- The SN-3 final-answer repair nudge, bounded to one corrective round
- The pytest deprecation-warning fix, landed in the first epic of this milestone

---

## Out of Scope

- The governance adapter itself (CF-3) — planned in M3
- The library entry point (CF-2)
- Broader CF-4 hardening beyond the repair nudge
- Any UI

---

## Planned Epics

### Confirmed Epics

- [E2.1 — write_file & list_dir Tools + Test Suite Housekeeping](P2-M2-E2.1__spec__write-file-list-dir-and-housekeeping.md) —
  `write_file` and `list_dir` with `allow_paths` scoping consistent with `read_file`/
  `edit_file`; fixes the carried-forward pytest deprecation warning
  (`tests/test_check_transcript.py::test_step`), per the Phase spec's direction that the fix
  land in P2's first epic.
- [E2.2 — git Tool & Subcommand Permission Scoping](P2-M2-E2.2__spec__git-tool-and-subcommand-scoping.md) —
  `git(args)` built-in with `allow_subcommands` enforcement; denied subcommands return
  deterministic tool-error messages (repair-loop inputs, not crashes).
- [E2.3 — Final-Answer Repair Nudge (SN-3)](P2-M2-E2.3__spec__final-answer-repair-nudge.md) —
  detects a junk/unusable terminating turn or ceiling-exhausted Q&A-shaped task and adds at
  most one bounded corrective round; §5 deterministic termination remains inviolable;
  unit-tested against recorded fixtures for both trigger conditions.

### Deferred Epics

- None.

---

## Completion Criteria

Milestone M2 is complete when all Epics under M2 are completed and closed.

Additionally:
- All three new tools pass permission-enforcement unit tests
- The repair nudge is unit-tested and provably bounded (never exceeds `max_iterations`)
- The pytest deprecation warning no longer appears in test suite output

---

## Acceptance Criteria

- [ ] `write_file` creates/overwrites files, scoped by `allow_paths`; denied paths return a
      deterministic tool-error message
- [ ] `list_dir` lists directory contents, scoped by `allow_paths`
- [ ] `git` executes only `allow_subcommands`-permitted subcommands; denied subcommands
      return a deterministic tool-error message
- [ ] `allow_paths` enforcement has identical semantics across `read_file`, `edit_file`,
      `write_file`, and `list_dir`
- [ ] The SN-3 repair nudge adds at most one corrective round, never exceeds
      `max_iterations`, and is unit-tested for both trigger conditions (junk terminating
      turn; Q&A ceiling exhaustion)
- [ ] `tests/test_check_transcript.py::test_step` uses `assert`, not `return` — no pytest
      deprecation warning in suite output
- [ ] Full test suite green, offline (no GPU required for any M2 epic)

---

## Dependencies

**Internal Dependencies:**
- E2.1 must land first — it carries the pytest housekeeping fix, which the Phase spec
  requires in P2's first epic
- E2.2 and E2.3 are mutually independent and may proceed in any order (or in parallel) once
  E2.1 is accepted
- M2 depends on P1 (M1) being closed — done, `v1.0.0`

**External Dependencies:**
- None. All M2 epics are testable against recorded/mocked responses; no GPU or live-model
  dependency (unlike P1's E1.5).

---

## Timeline

**Target Start:** TBD
**Target Completion:** TBD
**Actual Start:** 2026-07-10
**Actual Completion:** In progress

---

## Notes

- **Authoritative inputs:** CONTRACT.md v0.1 (§4 permission model; §5 deterministic
  termination — inviolable), the Phase spec (`docs/phases/P2__phase__first-real-run.md`),
  the 2026-07-10 Creation Chat steering note (SN-3, SN-4).
- **SN-3 constraint (encode in every Epic spec):** consumers MUST NOT depend on
  `final_answer`. The repair nudge improves usability but is not an adapter success signal —
  that's the exit code and the QA `validation_command`, M3's concern.
- **Milestone-level decision (2026-07-10):** the pytest housekeeping fix is bundled into
  E2.1 rather than given a standalone epic, per the Phase spec's explicit direction that it
  land in P2's first epic.
- **Process rule carried from P1 (CF-5):** issue Epic Delivery Authorizations *before*
  launching Coding Agents.
- **Host constraints (binding, unchanged from P1):** Ollama Docker-only over HTTP
  (`http://localhost:11434`), no `ollama` CLI; GPU contended with ComfyUI; the runner always
  runs inside a container (CONTRACT.md §10.3). None of M2's epics require the GPU.
