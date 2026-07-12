---
type: escalation-notice
milestone: M3
issued_by: Phase Chat (P2)
issued_to: HQ Chat
date: 2026-07-11
status: resolved
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

**HQ Chat decision (2026-07-11):** Hold. Phase P2 stays open with E3.2 unplanned until
`bin/run-dev-agent` is ready on the ai-project-system side. No interim/narrower path
(question 2) is authorized — the Brief's success criterion is to be met via the real
orchestrator-driven path, not a substitute. This is a wait-on-external-dependency
decision, not a scope change: nothing in the P2-M3 Milestone spec or the E3.1 deliverable
is reopened.

**Directive to Milestone Chat P2-M3:** Do not plan or launch E3.2 until this Phase Chat
notifies you that `bin/run-dev-agent` is ready. Milestone M3 remains open with E3.1 closed
and E3.2 pending; take no further action on E3.2 in the meantime.

**Phase Chat P2 follow-up:** this Phase Chat will monitor ai-project-system's Phase P7
scoping / P7-AE-1 status and re-open planning for E3.2 once `bin/run-dev-agent` lands. No
fixed check-in cadence was set — HQ will re-engage this Phase Chat when there's news, or
this Phase Chat surfaces status on request.

---

## Addendum — ai-project-system HQ Ruling received (2026-07-11)

Cross-repo answering authority has since ruled formally on this escalation:
`ai-project-system/.ai-project/artifacts/rulings/2026-07-11__ai-project-system-hq__ruling__p7-ae-1-adapter-unblocks-runner-p2.md`
(`blocking_resolved: true`). It **confirms** the hold above and adds firmness and a
coordination protocol — it does **not** lift the hold; P2 stays paused:

- **Bounded, not indefinite:** ai-project-system HQ commits to P7-AE-1 as a **flagship,
  early P7 deliverable**, scheduled first regardless of whatever spine the in-progress
  Creation Chat session picks for P7. The only remaining gate — the Creation Chat setting
  the P7 spine — is already in progress on that side; no dependency remains on anything
  from this project.
- **Decision 2 reaffirmed:** no interim/scripted path. CFO-ratified on the
  ai-project-system side independently: a scripted bypass would leave the Brief's
  acceptance criterion unmet and have to be redone.
- **Execution sequence committed:** deliver `bin/run-dev-agent` → flip `epic_dev` from
  `llama3:8b` to `qwen2.5-coder:14b` in `.ai-project.yml` → wire this runner as
  `dev_command`, drop the `04_epic.json` mock trigger → execute one live Epic
  end-to-end.
- **Coordination mechanism for closing E3.2 (new — record for the Milestone Chat):** the
  single live-run execution of P7-AE-1 *is* E3.2's evidence. ai-project-system runs it and
  writes the transcript into that Epic's own artifacts; that run is then **surfaced to
  this project's P2-M3 Milestone Chat for acceptance** (the Brief requires acceptance in
  the runner's own parent Milestone Chat, not on the ai-project-system side). Only on that
  acceptance does E3.2 → M3 → P2 close, in sequence.
- **SN-3 reaffirmed by the answering side too:** the adapter MUST NOT depend on
  `final_answer` — epic success is the QA `validation_command` exit code and the
  transcript.
- **Flagged, not a blocker:** GPU/VRAM contention between this runner's Ollama use and
  ComfyUI (SN-17 carry-over) is noted for ai-project-system's P7 scoping, but explicitly
  not a blocker for P7-AE-1 (Ollama-only, no ComfyUI dependency for the first run).

No further escalation is required — this addendum closes the loop the Ruling asked for
("the runner's Phase Chat may mark its escalation resolved on receipt"). The hold itself
remains in force until `bin/run-dev-agent` actually lands.
