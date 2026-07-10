---
artifact_type: steering_note
artifact_version: 1.0
timestamp: 2026-07-10T23:30:00Z
issuer_chat: Creation Chat
target: HQ Chat
project_name: local-agent-runner
concerns:
  - id: SN-3
    severity: medium
    title: Final-answer turn is unreliable on Q&A-shaped tasks with qwen2.5-coder:14b
  - id: SN-4
    severity: low
    title: CF-3 adapter work spans two repos (runner-side here, adapter Epic in ai-project-system)
decisions:
  - "P2 scope ratified: CF-1 (write_file, list_dir, git tools + full permission model) + CF-3 (bin/run-dev-agent adapter support) + targeted CF-4 hardening (final-answer repair nudge). CF-2 (library entry point) deferred."
  - "P2 exit criterion: the first REAL agentic run — a live Epic through the ai-project-system orchestrator with this runner as dev_command — succeeds."
---

# Steering Note — Creation Chat to HQ Chat

## Purpose

Answers the open decision in HQ's Progress Digest (2026-07-10): the CFO has ratified Phase 2
scope. The decision is grounded in an external audit of v1.0.0 performed inside the
ai-project-system project (recorded in that project's memory as
`local-model-epic-execution.md`, 2026-07-10, verdict: "ready to move forward"), which the CFO
has endorsed as the input for P2. This note hands HQ the scope, the audit's new findings, and
the exit criterion.

---

## Concerns for HQ Triage

### SN-3 — Final-answer turn unreliable on Q&A-shaped tasks [MEDIUM]

**Detail:** The audit's live smoke test of v1.0.0 found tool calls work perfectly (right
tool/args, permission-scoped, clean transcripts and exit codes), but on Q&A-shaped tasks the
final-answer turn is systematically unreliable with `qwen2.5-coder:14b` — it echoes a junk
`{"name":null}` blob as the answer, or re-calls `read_file` until `max_iterations`. Not a
blocker for epic execution (success there is the QA `validation_command` exit code, not
prose), but two consequences bind P2: (a) the `bin/run-dev-agent` adapter MUST NOT depend on
`final_answer`; (b) P2 should add a repair nudge for the final-answer turn.

**Required action:** Encode both consequences as constraints in the P2 phase spec.

### SN-4 — CF-3 spans two repos [LOW]

**Detail:** Per CONTRACT §7, `bin/run-dev-agent` is Epic-shaped work *inside ai-project-system*;
the runner side only needs to support it. The ai-project-system side is already staged: its
orchestrator's Agentic Mode passed all 5 verify-loop scenarios end-to-end with mocked dev/QA —
the runner is the only remaining variable. Wiring steps recorded there: deliver the runner →
wire as `dev_command` → drop the `04_epic.json` trigger; also update that repo's
`.ai-project.yml` `epic_dev` from `llama3:8b` (proven unusable for tools) to
`qwen2.5-coder:14b`.

**Required action:** Scope P2 here to the runner-side support only; the adapter Epic itself
must be planned in ai-project-system's governance.

---

## Decisions Already Made

1. **P2 scope (CFO-ratified):** from the Progress Digest's carry-forward list —
   - **CF-1:** the missing tools a real epic needs — `write_file`, `list_dir`, `git` (audit:
     "read_file+edit_file+run_command can't create files") — plus the full permission model.
   - **CF-3:** runner-side support for the `bin/run-dev-agent` adapter (see SN-4 for the
     cross-repo boundary).
   - **CF-4 (targeted):** the final-answer repair nudge from SN-3.
   - **CF-2 (library entry point): deferred** — nothing in the audit or the first-real-run
     path requires it. (CFO-confirmed in Creation Chat, 2026-07-10.)
2. **P2 exit criterion:** the first REAL agentic run succeeds — a live Epic executed through
   ai-project-system's orchestrator with this runner as `dev_command`, accepted per the
   project Brief's success criterion. (CFO-confirmed in Creation Chat, 2026-07-10.)

---

## Carry-Over Open Items

1. The pytest deprecation-warning fix (`test_check_transcript.py::test_step` returns instead
   of asserts) — already slated by the Progress Digest to fold into the first P2 epic.

---

## Next Action

HQ Chat should:
1. Draft the P2 phase spec with the SN-3 constraints encoded.
2. Issue the P2 Phase Execution Chat Starter.
3. Coordinate with ai-project-system's HQ for the adapter Epic on their side (SN-4).
