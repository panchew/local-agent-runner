---
project: local-agent-runner
phase: P2
milestone: M3
type: milestone
status: on-hold
last_updated: 2026-07-11
---

# Milestone M3 — Adapter Readiness & First Real Run

## Purpose

Close the last gap between the runner and the `bin/run-dev-agent` adapter shim
(CONTRACT.md §7), verify the runner-side contract against the shim's actual invocation
pattern, then execute the Phase's exit event: a live Epic run through
ai-project-system's orchestrator with this runner as `dev_command`, accepted per the
project Brief's success criterion.

This milestone ensures:
- The adapter shim can build a Task the way §7 describes it (`--task` = DoD,
  `--context` = scoped epic spec/starter, `--tools` = coding set, `--model` = the active
  tag) and get back a runner invocation that behaves exactly as documented
- The adapter-facing contract never leans on `final_answer` (SN-3) — only the exit code
  and transcript are load-bearing
- The founding question of P2 — can this engine carry a *real* Epic, not just a proof
  fixture? — is answered by a live, accepted run

---

## Problem Statement

M2 gave the runner every tool a real Epic needs, but the runner still cannot receive
scoped context the way the adapter shim is specified to send it: `--context` exists as
an internal `run()` parameter (per §5) but is not exposed on the CLI — P1 explicitly
deferred it ("the CLI does not surface them in M1"). Until that gap closes and is
verified against the shim's exact invocation shape, the adapter Epic on the
ai-project-system side has nothing real to integrate against, and the Brief's success
criterion — a live, accepted Epic run — remains unproven.

---

## Goals

By the end of this milestone, the system must:

1. Expose `--context` on the CLI (file-based, mirroring the existing `--task` /
   `--task-text` pattern), wired to the `run()` function's existing `context` parameter
2. Confirm exit codes 0/2/3/4 and the `--transcript` JSON (§3 Result shape) are stable
   and sufficient for the adapter to consume without ever reading `final_answer` (SN-3)
3. Prove the above against a fixture that reproduces the adapter shim's exact
   invocation pattern (§7 step 2: `--task` = an epic's Definition of Done text,
   `--context` = a scoped epic spec/starter excerpt, `--tools` = a coding-set
   `tools.json` scoped to a repo, `--model` = an explicit tag) — offline, no GPU
   required
4. Execute the first REAL agentic run: a live Epic through ai-project-system's
   orchestrator with this runner as `dev_command`, accepted in its parent Milestone
   Chat on that side — the project Brief's success criterion

---

## Non-Goals

This milestone explicitly does **not** aim to:

- Build `bin/run-dev-agent` itself — per CONTRACT.md §7 and SN-4 that shim is Epic-shaped
  work *inside ai-project-system*, planned under that project's governance; M3 delivers
  only the runner-side support it consumes
- Expose `--system` on the CLI — the §7 shim's invocation pattern does not use it; adding
  it now would be scope beyond what this milestone's dependency requires
- Pursue CF-2 (library entry point) or broader CF-4 hardening
- Modify anything already closed in M2 (tools, permission model, repair nudge)
- Any UI

---

## In Scope

- The `--context` CLI flag and its wiring to `run()`
- Verification (fixture-based, offline) that the runner's exit codes and transcript
  shape satisfy the adapter shim's needs without depending on `final_answer`
- The live Epic run through ai-project-system's orchestrator (execution, not runner
  code) and its acceptance record

---

## Out of Scope

- The `bin/run-dev-agent` adapter Epic itself (ai-project-system's governance, SN-4)
- `--system` CLI exposure
- CF-2, broader CF-4, any UI

---

## Binding Constraints (SN-3, carried from the Phase spec)

1. **Consumers MUST NOT depend on `final_answer`.** The adapter-facing verification in
   E3.1 must demonstrate success using only the exit code and transcript — never by
   reading `final_answer`.
2. The SN-3 repair nudge (already delivered in M2/E2.3) remains bounded to one
   corrective round; nothing in M3 may reopen or weaken it.

---

## Planned Epics

### Confirmed Epics

- [E3.1 — CONTRACT §7 Runner-Side Adapter Verification](P2-M3-E3.1__spec__contract-section-7-adapter-verification.md) —
  add the `--context` CLI flag; build an offline fixture reproducing the adapter shim's
  exact invocation pattern; confirm exit codes and transcript shape are the adapter's
  only required signals (SN-3).
- [E3.2 — First Real Run](P2-M3-E3.2__spec__first-real-run.md) —
  the live Epic executed through ai-project-system's orchestrator with this runner as
  `dev_command`, accepted per the Brief's success criterion. **Gated on the cross-repo
  adapter Epic (SN-4)** — see Dependencies.

### Deferred Epics

- None.

---

## Completion Criteria

Milestone M3 is complete when both Epics are completed and closed.

Additionally:
- The first REAL agentic run has succeeded and been accepted (the Phase's exit event)

---

## Acceptance Criteria

- [ ] `--context` reads a file and is passed through to `run()`'s existing `context`
      parameter; unit-tested
- [ ] A fixture reproducing the adapter shim's exact invocation pattern (DoD-shaped
      task, scoped context, coding-set tools, explicit model tag) runs the CLI
      end-to-end offline and succeeds using only exit code + transcript — never
      `final_answer`
- [ ] Exit codes 0/2/3/4 and the `--transcript` §3 Result shape are unchanged from M2
      (no regression) and documented as the adapter's success/failure signals
- [ ] A live Epic has been executed through ai-project-system's orchestrator with this
      runner as `dev_command` and accepted in its parent Milestone Chat
- [ ] Full test suite green, offline, for E3.1 (no GPU required); E3.2's proof is
      necessarily a live run and is evidenced by the accepted transcript, not a unit
      test

---

## Dependencies

**Internal Dependencies:**
- E3.2 depends on E3.1 (the adapter contract must be verified before it is exercised
  live)
- M3 depends on M2 being closed — done, `0e1b802` on `phase/P2`

**External Dependencies (SN-4 — binding):**
- E3.2 requires the adapter Epic on the **ai-project-system** side: wiring this runner
  as `dev_command`, dropping the `04_epic.json` trigger, and updating that repo's
  `epic_dev` model from `llama3:8b` to `qwen2.5-coder:14b`. That work is planned and
  executed under ai-project-system's own governance — this Phase Chat does not build it
  or reach across repos to accelerate it.
- **If the adapter Epic is not ready when E3.2 is otherwise ready to launch, the Phase
  Chat escalates to HQ Chat** rather than proceeding laterally. HQ-to-HQ coordination
  between the two projects happens at the human layer.

---

## Timeline

**Target Start:** TBD
**Target Completion:** TBD
**Actual Start:** 2026-07-11
**Actual Completion:** In progress

---

## Notes

- **Authoritative inputs:** CONTRACT.md v0.1 (§7 adapter shim; §5 `context` parameter
  already implemented; §3 Result shape), the Phase spec
  (`docs/phases/P2__phase__first-real-run.md`), the 2026-07-10 Creation Chat steering
  note (SN-3, SN-4), and the P2-M2 Closure Declaration (carry-forward: tool surface and
  repair nudge are done; nothing in M3 reopens them).
- **Scope-narrowing decision (2026-07-11):** `--system` is excluded from M3 because the
  §7 shim's documented invocation pattern does not use it — adding it would be scope
  beyond what this milestone's dependency (the adapter shim) requires. Revisit only if a
  future consumer needs it.
- **Process rule carried from P1 (CF-5):** issue Epic Delivery Authorizations *before*
  launching Coding Agents.
- **This is the Phase's exit milestone.** When E3.2 is accepted, Phase P2 meets its Exit
  Criteria per the Phase spec and should proceed to Phase Closure.
- **On hold (2026-07-11):** E3.1 is closed; E3.2 is blocked on the SN-4 cross-repo
  dependency (the `bin/run-dev-agent` adapter Epic does not yet exist on
  ai-project-system's side — see
  `P2-M3__escalation-notice__e3-2-sn-4-blocked.md`). HQ decision, relayed via
  `P2__escalation-notice__m3-e3-2-sn-4-blocked.md`: hold until `bin/run-dev-agent` is
  ready; no interim/narrower path authorized. Do not plan or launch E3.2 until the Phase
  Chat lifts this hold. Not a scope change — nothing above this note is amended.
- **Cross-repo ruling received (2026-07-11):** ai-project-system HQ ruled
  (`ai-project-system/.ai-project/artifacts/rulings/2026-07-11__ai-project-system-hq__ruling__p7-ae-1-adapter-unblocks-runner-p2.md`,
  `blocking_resolved: true`) that P7-AE-1 (the adapter Epic) is committed as a flagship,
  early P7 deliverable, scheduled first once that side's Creation Chat sets the P7 spine
  (already in progress) — the hold is bounded, not indefinite. **Coordination protocol
  for closing E3.2, once the adapter lands:** ai-project-system executes P7-AE-1 as one
  live end-to-end Epic run and writes its transcript into that Epic's own artifacts; that
  run is then surfaced to **this Milestone Chat (P2-M3) for acceptance** — the Brief
  requires acceptance in the runner's own parent Milestone Chat, not on the
  ai-project-system side. Only on that acceptance does E3.2 close, followed by M3 and
  P2. No interim/scripted path was authorized (reaffirmed by both sides independently).
