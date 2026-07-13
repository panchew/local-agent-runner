---
project: local-agent-runner
phase: P2
milestone: M3
type: closure-declaration
status: stage-1-complete
closure_date: 2026-07-13
---

# MILESTONE CLOSURE DECLARATION — P2-M3

**Milestone:** M3 — Adapter Readiness & First Real Run
**Phase:** P2 — First Real Run
**Status:** Stage 1 complete (below); Stage 2 (consolidation to `phase/P2`) awaits Phase
Chat acceptance
**Completion Date:** 2026-07-13
**Declared By:** Milestone Chat P2-M3 (Stage 1); Phase Chat P2 acceptance pending for
Stage 2
**Merge Commit:** N/A yet — `milestone/M3` has not been consolidated into `phase/P2`

> This document is the authoritative record of P2-M3's Stage 1 completion, including the
> acceptance of externally-produced (cross-repo) evidence for E3.2. Chat is ephemeral —
> this artifact is the record.

---

## Stage 1: Completion Verification

✅ **E3.1 — CONTRACT §7 Runner-Side Adapter Verification** — merged to `milestone/M3`
(`40610f0`, merge `5db0094`). `--context` exposed on the CLI, wired to `run()`'s existing
parameter; adapter-shape fixture proves exit codes + transcript are sufficient without
ever reading `final_answer`. 209 passed / 1 skipped, independently re-verified.

✅ **E3.2 — First Real Run** — accepted on the strength of **cross-repo evidence produced
by ai-project-system**, not work performed in this repository. Full chain:

1. **The hold (SN-4):** P2 was held pending ai-project-system's own adapter Epic. See
   `P2__escalation-notice__m3-e3-2-sn-4-blocked.md` and
   `P2-M3__escalation-notice__e3-2-sn-4-blocked.md` (both `status: resolved`).
2. **The ai-project-system HQ Ruling** (2026-07-11,
   `ai-project-system/.ai-project/artifacts/rulings/2026-07-11__ai-project-system-hq__ruling__p7-ae-1-adapter-unblocks-runner-p2.md`)
   committed P7-AE-1 (the adapter Epic) as a flagship, scheduled-first P7 deliverable and
   set the coordination protocol: their live run's transcript would be surfaced here for
   acceptance.
3. **The cross-repo hand-back**
   (`ai-project-system/docs/phases/P7__Agentic_Execution_and_Default_On_Visuals/P7-M26__escalation-notice__cross-repo-hand-back-p2-m3.md`)
   delivered the evidence: ai-project-system's Milestone P7-M26 executed `bin/run-dev-agent`
   (E26.1), wired a real tool-calling model (E26.2), and ran one live, non-mocked Epic
   through `bin/ai-project-orchestrator` with this runner as `dev_command` (E26.3).

**This Milestone Chat independently re-verified the evidence — not trusted from the hand-back's
claims alone:**

- Confirmed `milestone/M3` (this branch, `b5a848b`) contains `40610f0` (`--context`);
  re-ran the full suite on this exact ref: **209 passed, 1 skipped**.
- Read the run record
  (`ai-project-system/docs/phases/P7__Agentic_Execution_and_Default_On_Visuals/P7-M26-E26.3__run-record.md`),
  `transcript.json`, and `run-metadata.json` directly (not summarized secondhand):
  - `run-metadata.json`: `exit_code: 0`, `runner` = a wrapper invoking
    `python3 -m local_agent_runner` with `PYTHONPATH` pointed at a `git worktree` of *this
    repo's* `milestone/M3` — confirmed this is genuinely this project's own code being
    exercised, not a stand-in.
  - `transcript.json`: `status: "completed"`, 7 tool-call rounds (`iterations: 7`, matching
    CONTRACT §3's "number of tool-call rounds" definition — the terminating no-tool-call
    round is not itself counted, but its ~14 tokens are folded into the `tokens: 404` total,
    reconciling against the 390 summed from the 7 logged `eval_count`s: no discrepancy).
  - **`final_answer` was the identical boilerplate refusal** ("I'm sorry, but I can't assist
    with that request.") on the very attempt that converged — confirmed directly in
    `transcript.json`. Success was determined solely by the QA `validation_command`
    (`pytest tests/test_ai_project_version_script.py`, exit 0), never by `final_answer` —
    SN-3 honored, and dramatically so: judging by `final_answer` would have misreported a
    genuine success as a failure.
- Independently confirmed the three real blockers ai-project-system found and fixed were
  **on their side, not this repo's**:
  - Sandbox/Docker unreachability and the `--context`-flag branch gap are ai-project-system
    execution-environment and cross-repo ref choices — nothing in this repo needed to
    change for either.
  - The `allow_paths` glob bug (`"./**"` never matching `Path.resolve()`'s always-absolute
    output) is a **config-value bug in ai-project-system's own `.ai-project/agents/
    tools.json`**, not a defect in this repo's `tools.py`. Read `path_permitted()`
    directly (`local_agent_runner/tools.py:176-180`): it resolves to an absolute path and
    matches via `fnmatchcase`, exactly as documented (CONTRACT §4's own example glob is
    absolute-style, `/repo/**`) and exactly as this repo's own M2 tests already cover. No
    fix, note, or follow-up needed on this side — confirmed by inspection, not merely
    accepting the hand-back's characterization.
- Confirmed the evidence was produced against **this repo's `milestone/M3`, not
  `phase/P2`** — disclosed plainly by the hand-back and independently reproducible: `git
  merge-base --is-ancestor 40610f0 phase/P2` fails; the same check against `milestone/M3`
  succeeds. This is exactly why Stage 2 (below) consolidates `milestone/M3` into
  `phase/P2` now — closing the gap the evidence was produced across.

✅ **Milestone acceptance criteria satisfied** (Milestone spec, verified against
committed evidence):

1. `--context` reads a file and reaches `run()`'s `context` parameter unchanged — ✅
   (E3.1, unit-tested; also exercised live in the accepted run's `context.md` seeding)
2. The adapter-shape fixture proves exit codes + transcript sufficient without
   `final_answer` — ✅ (E3.1, offline fixture; independently reconfirmed live by the
   accepted run itself, per above)
3. Exit codes 0/2/3/4 and the `--transcript` shape unchanged from M2 — ✅ (E3.1; no
   regression, 209/1 unchanged in count-plus-new-tests terms from M2's 202/1 plus E3.1's 7
   new tests)
4. A live Epic executed through ai-project-system's orchestrator with this runner as
   `dev_command`, accepted in its parent Milestone Chat — ✅ (E3.2, accepted here, this
   document)

✅ **Completion criteria:** both Epics closed; the first REAL agentic run succeeded and is
accepted (the Phase's exit event).

---

## Milestone Summary

M3 closed the last runner-side gap (E3.1: `--context` on the CLI) and then answered P2's
founding question — can this engine carry a *real* Epic? — via genuine cross-repo evidence
rather than new code in this repository: ai-project-system built the adapter it owns
(CONTRACT §7, SN-4), wired a real tool-calling model, and ran one live, non-mocked Epic
end to end, converging on attempt 1 of 3 after finding and fixing three real blockers (two
on their side, none requiring any change here). SN-3 was not just honored but *proven
necessary*: the converging run's own `final_answer` was a refusal boilerplate that would
have misreported success as failure had it been consulted.

---

## Record: Epic Delivery Authorizations

| Epic | Authorization date | Note |
|------|--------------------|------|
| E3.1 | 2026-07-11 | recorded retroactively, per the P1/M2 precedent |
| E3.2 | 2026-07-13 | evidence produced and delivered entirely by ai-project-system's own governance chain (P7-M26); no Coding Agent was launched in this repository for E3.2 |

---

## Stage 2: Closure Confirmation (consolidation) — NOT YET PERFORMED

Stage 2 (`milestone/M3` → `phase/P2` consolidation) is a Phase-level acceptance decision,
not the Milestone Chat's to self-authorize.

**Awaiting from Phase Chat P2:**
- [ ] Milestone-level acceptance of P2-M3 as a whole
- [ ] Authorization to merge `milestone/M3` → `phase/P2`

## Next Steps

- Once Phase Chat P2 accepts, consolidate `milestone/M3` → `phase/P2` and re-run the full
  suite post-merge
- M3 is P2's exit milestone (per the Milestone spec's own Notes): once consolidated, Phase
  P2 meets its Exit Criteria and Phase Closure (PROJECT-SYSTEM-GUIDELINES.md §5C) follows
- `epic/E3.1` and `milestone/M3` branches (and the cross-repo `git worktree` ai-project-system
  used to pin this evidence) retained as history; archive or delete per project policy
