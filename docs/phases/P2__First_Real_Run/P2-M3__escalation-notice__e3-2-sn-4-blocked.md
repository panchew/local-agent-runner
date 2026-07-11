---
type: escalation-notice
milestone: M3
issued_by: Milestone Chat (P2-M3)
issued_to: Phase Chat (P2)
date: 2026-07-11
status: resolved
---

# Escalation Notice: E3.2 blocked on the SN-4 cross-repo adapter Epic

## Trigger

Cross-milestone/cross-repo dependency outside this Milestone Chat's authority. E3.1
(CONTRACT §7 Runner-Side Adapter Verification) is complete and merged to `milestone/M3`.
E3.2 (First Real Run) is next in the Milestone spec's binding dependency order, but
E3.2's external dependency (SN-4) — the adapter Epic on the **ai-project-system** side
(wiring this runner as `dev_command`, dropping the `04_epic.json` trigger, updating that
repo's `epic_dev` model from `llama3:8b` to `qwen2.5-coder:14b`) — is not ready. Per the
Milestone spec's binding instruction, an unready SN-4 dependency escalates to the Phase
Chat rather than being resolved by this Milestone Chat reaching across repos.

## What Was Attempted

- Confirmed E3.1 accepted (DoD verified, 209 passed/1 skipped reproduced independently,
  SN-3 respected, merged to `milestone/M3`).
- Checked SN-4 readiness via the ai-project-system Creation Chat before planning E3.2, as
  required before authorizing E3.2's launch. Reported back:
  - `bin/run-dev-agent` does not exist on `master` in ai-project-system.
  - `epic_dev` is still `llama3:8b` (not yet `qwen2.5-coder:14b`).
  - The adapter work is only a **roadmap candidate** (P7-AE-1, GitHub issue #111) —
    Phase P7 itself is unscoped.
  - P7-AE-1 is itself gated on this project's P2 tool epics — which just closed with
    M2 and E3.1.
- Did not proceed to plan or draft E3.2's Epic spec/starter, and did not reach into
  ai-project-system's repo or governance to build or accelerate the adapter Epic — both
  explicitly out of this Milestone Chat's authority (SN-4 boundary).

## Decision Needed

A cross-repo, HQ-layer coordination decision this Milestone Chat cannot make:

1. Should Phase P2 hold open (E3.2 unplanned) until ai-project-system scopes Phase P7
   and executes P7-AE-1? If so, what unblocks P7 being scoped — is that itself waiting
   on something from this project, or a separate prioritization decision on the
   ai-project-system side?
2. Is there a narrower interim path (e.g., a manual/scripted first run that doesn't
   require the full `bin/run-dev-agent` adapter) that would satisfy the Brief's success
   criterion without waiting on P7-AE-1, or does the Brief specifically require the
   orchestrator-driven path?

## Impact

Milestone M3 cannot close — E3.2 is the Milestone's second Epic and the Phase's exit
event (per the Milestone spec: "This is the Phase's exit milestone. When E3.2 is
accepted, Phase P2 meets its Exit Criteria"). Phase P2 cannot proceed to Phase Closure
until this resolves. Nothing else in this Milestone is blocked — E3.1's deliverables
stand on their own and required no further work.

## Resolution

**Phase Chat decision (2026-07-11), relaying HQ's:** Hold. Phase P2 stays open with E3.2
unplanned until `bin/run-dev-agent` is ready on the ai-project-system side. No interim or
narrower path is authorized — the Brief's success criterion is to be met via the real
orchestrator-driven path only. Full record:
`docs/phases/P2__First_Real_Run/P2__escalation-notice__m3-e3-2-sn-4-blocked.md`
(Phase Chat → HQ Chat, resolved).

**Directive to this Milestone Chat:** Do not plan or launch E3.2 until the Phase Chat
notifies you that `bin/run-dev-agent` is ready. Milestone M3 remains open — E3.1 closed,
E3.2 pending — take no further action on E3.2 in the meantime. This is a wait, not a scope
change: the Milestone spec is unamended.
