---
type: escalation-notice
milestone: M3
issued_by: Phase Chat (P2)
issued_to: HQ Chat
date: 2026-07-11
status: open
---

# Escalation Notice: E3.2 blocked on the SN-4 cross-repo adapter Epic (relayed from Milestone M3)

## Trigger

Cross-repo, HQ-layer coordination decision outside this Phase Chat's authority. Milestone
Chat P2-M3 escalated to this Phase Chat
(`docs/phases/P2__First_Real_Run/P2-M3__escalation-notice__e3-2-sn-4-blocked.md`, still
`status: open`) because E3.2 (First Real Run) — the Phase's exit event — cannot be planned
or launched: its external dependency (SN-4), the adapter Epic on the **ai-project-system**
side, is not ready. Per this Phase Chat's own governing starter ("if M3 is blocked on it,
escalate to HQ Chat — it does not reach across repos"), this Phase Chat cannot resolve a
cross-repo prioritization question either, and relays it upward rather than reaching into
ai-project-system's repo or governance itself.

## What Was Attempted

- Reviewed Milestone Chat P2-M3's Escalation Notice and independently confirm its factual
  basis is consistent with the Milestone spec's SN-4 dependency note and the Phase spec's
  own binding constraint ("If the adapter Epic is not ready when M3 needs it, the Phase
  Chat escalates to HQ — it does not reach across repos").
- Confirmed E3.1 (CONTRACT §7 Runner-Side Adapter Verification) is complete and merged to
  `milestone/M3` — this Phase's runner-side obligations under CF-3 are fully met; the gap
  is entirely on the ai-project-system side.
- Did not attempt to plan E3.2, reach into ai-project-system's repository or governance, or
  otherwise resolve the SN-4 readiness gap directly — all explicitly out of this Phase
  Chat's authority per its own starter.

## Decision Needed

Relaying the Milestone Chat's two questions, since only HQ can make a cross-project call:

1. Should Phase P2 hold open (E3.2 unplanned) until ai-project-system scopes Phase P7 and
   executes P7-AE-1 (the adapter work, currently only a roadmap candidate — GitHub issue
   #111 — gated on this project's P2 tool epics, which just closed)? If so, what unblocks
   P7 being scoped, and on what timeline?
2. Is there a narrower interim path — e.g., a manual or scripted first run that doesn't
   require the full `bin/run-dev-agent` adapter — that would satisfy the project Brief's
   success criterion without waiting on P7-AE-1? Or does the Brief specifically require the
   orchestrator-driven path, making no interim path acceptable?

## Impact

Milestone M3 cannot close (E3.2 is its second Epic). Phase P2 cannot reach Phase Closure
until M3 closes — the Phase spec names the first real orchestrator-driven run as an
explicit Exit Criterion. Nothing else is blocked: M2 is fully closed, and E3.1's
deliverables stand on their own regardless of how this resolves.

## Resolution

(empty — awaiting HQ Chat decision)
