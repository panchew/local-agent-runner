---
project: local-agent-runner
phase: P2
milestone: M2
type: closure-declaration
status: stage-1-complete
closure_date: 2026-07-10
---

# MILESTONE CLOSURE DECLARATION — P2-M2

**Milestone:** M2 — Real-Epic Toolset
**Phase:** P2 — First Real Run
**Status:** Stage 1 complete (below); Stage 2 (consolidation to `phase/P2`) awaits Phase
Chat acceptance
**Completion Date:** 2026-07-10
**Declared By:** Milestone Chat P2-M2 (Stage 1); Phase Chat P2 acceptance pending for
Stage 2
**Merge Commit:** N/A yet — `milestone/M2` has not been consolidated into `phase/P2`

> This document is the authoritative record of P2-M2's Stage 1 completion. The
> acceptance decisions and review verdicts summarized here were issued in the Milestone
> Chat session (2026-07-10); chat is ephemeral — this artifact is the record.

---

## Stage 1: Completion Verification

✅ **All Epics complete and merged to `milestone/M2`:**

| Epic | Name | Feature/notice commits | Accepted & merged |
|------|------|-------------------------|-------------------|
| E2.1 | write_file & list_dir Tools + Test Suite Housekeeping | `ab22ed2` | merge `e6eef96` |
| E2.2 | git Tool & Subcommand Permission Scoping | `439c70e`, `ec39821` | merge `98bc692` |
| E2.3 | Final-Answer Repair Nudge (SN-3) | `4f5cb78`, `373b2ec` | merge `430e9f6` |

✅ **All Epics accepted:** each delivery was independently verified by the Milestone
Chat (tests re-run myself, diffs read in full against the Epic spec, no reliance on the
Delivery Notice's claims alone) and accepted as a clean delivery per
PROJECT-SYSTEM-GUIDELINES.md §11.6 (acceptance by silence; no Review Decision was
required for any Epic). Each Epic's Delivery Notice is committed alongside its spec.
Every merge was performed only after explicit human confirmation in-session (the
permission layer flagged self-merge-after-self-review as a decision requiring that
confirmation; it was sought and given for all three Epics).

✅ **Milestone acceptance criteria satisfied** (Milestone spec, verified against
committed evidence):

1. `write_file` creates/overwrites files, scoped by `allow_paths`; denied paths return a
   deterministic tool-error message — ✅ (E2.1)
2. `list_dir` lists directory contents, scoped by `allow_paths` — ✅ (E2.1)
3. `git` executes only `allow_subcommands`-permitted subcommands; denied subcommands
   return a deterministic tool-error message — ✅ (E2.2, denial proven to precede
   `subprocess.run` via a monkeypatch that fails the test if invoked)
4. `allow_paths` enforcement has identical semantics across `read_file`, `edit_file`,
   `write_file`, and `list_dir` — ✅ (E2.1, `TestFileToolsPathConsistency`: same denied
   path and same `..`-traversal path denied identically by all four tools)
5. The SN-3 repair nudge adds at most one corrective round, never exceeds
   `max_iterations`, and is unit-tested for both trigger conditions — ✅ (E2.3, `status`
   provably never changed by the nudge in either branch; `len(calls) ==
   max_iterations + 1` asserted exactly, never more)
6. `tests/test_check_transcript.py::test_step` uses `assert`, not `return` — no pytest
   deprecation warning in suite output — ✅ **via rename, not literal conversion** (E2.1
   renamed the value-returning builder `test_step` → `run_step`, removing it from
   pytest's `test_*` collection entirely — the correct fix, since the function is a
   builder consumed by ~20 call sites, not an assertion; converting it to `assert`
   would have broken every caller). Verified: `pytest -W
   error::pytest.PytestReturnNotNoneWarning` passes clean.
7. Full test suite green, offline (no GPU required for any M2 epic) — ✅ **202 passed, 1
   skipped**, re-run independently on merged `milestone/M2` (not just trusted from
   Delivery Notices)

✅ **Completion criteria:** all three Epics closed and merged to `milestone/M2`; the
repair nudge is unit-tested and provably bounded; the pytest deprecation warning is
gone.

---

## Milestone Summary

M2 gave the runner the remaining CONTRACT.md §4 tool surface a real Epic needs:
`write_file` and `list_dir` (E2.1, plus the carried-forward pytest housekeeping fix),
`git` with `allow_subcommands` scoping executed without a shell (E2.2), and the SN-3
final-answer repair nudge bounded to at most one corrective, tools-disabled call that
never changes `status` (E2.3). 47 new/updated tests landed across the three Epics (155
→ 202 passed), all offline — no GPU or live-model dependency anywhere in M2, unlike
P1's E1.5. The engine can now create files, inspect directories, commit work via git,
and gives a real Q&A-shaped task a usable terminating answer without weakening §5's
deterministic termination or promoting `final_answer` to a signal M3's adapter could
mistakenly depend on.

---

## Record: Epic Delivery Authorizations

Per CF-5 (carried from P1), Epic Delivery Authorizations should be issued **before**
launching a Coding Agent. As in P1-M1, execution in this session was parent-launched
ahead of the formal authorization step for all three Epics; recorded retroactively here
for permanence, following the P1-M1 precedent.

| Epic | Authorization date | Note | Merge instruction outcome |
|------|--------------------|------|----------------------------|
| E2.1 | 2026-07-10 | recorded retroactively | executed — `e6eef96` |
| E2.2 | 2026-07-10 | recorded retroactively | executed — `98bc692` |
| E2.3 | 2026-07-10 | recorded retroactively | executed — `430e9f6` |

Process note carried forward (unresolved since P1): issue the Epic Delivery
Authorization **before** launching the Coding Agent, per the Milestone Execution Chat
Starter — this has now recurred across two milestones and may warrant a Phase- or
Creation-Chat-level process fix rather than a repeated per-milestone note.

---

## Stage 2: Closure Confirmation (consolidation) — NOT YET PERFORMED

Stage 2 (`milestone/M2` → `phase/P2` consolidation) is a Phase-level acceptance
decision, not the Milestone Chat's to self-authorize (per this Milestone's own
governance references: "milestone-level acceptance belongs to the parent chat").

**Awaiting from Phase Chat P2:**
- [ ] Milestone-level acceptance of P2-M2 as a whole
- [ ] Authorization to merge `milestone/M2` → `phase/P2`

## Next Steps

- Once Phase Chat P2 accepts, consolidate `milestone/M2` → `phase/P2` and re-run the
  full suite post-merge before declaring Stage 2 closed
- Any future `milestone/M3` MUST branch from `phase/P2` (post-consolidation commit)
- `epic/E2.1`–`epic/E2.3` and `milestone/M2` branches retained as history; archive or
  delete per project policy
