---
type: phase-closure-declaration
phase: P2
name: First Real Run
status: closed
merge_commit: 367bd23
tag: v2.0.0
main_head_at_closure: 367bd23
closed_date: 2026-07-13
closed_by: Phase Chat (P2); consolidated and accepted by HQ Chat
acceptance_model: SN-13 default-accept — explicit HQ acceptance given in-session 2026-07-13; no Review Decision artifact required
---

# Phase P2 Closure Declaration

**Phase P2 — First Real Run is closed.**

Merge commit `367bd23` landed on `main` (no-ff merge of `phase/P2`, per the P1 no-remote
adaptation — this repo has no hosted remote to open a PR against). Tagged `v2.0.0`.

> This document is Stage 1 of the phase-closure record (PSG §5C Steps 1–4, prepared by
> the Phase Chat) plus Stage 2 (PSG §5C Steps 5, 7, 8, 9 — the `phase/P2` → `main` merge,
> the `v2.0.0` tag, and this sign-off), performed by HQ Chat under CFO authorization
> (`governance/systems/roles-authorization-team-governance.md`, "Merging to Branches").

---

## Stage 1: Phase Complete (PSG §5C Steps 1–4) — done by Phase Chat

**Step 1 — All Milestones fully closed:**

| Milestone | Epics | Scope closed | Merge commit (→ `phase/P2`) |
|-----------|-------|---------------|------------------------------|
| M2 — Real-Epic Toolset | E2.1–E2.3 (3) | `write_file`/`list_dir`/`git` + full CONTRACT §4 permission model; SN-3 repair nudge; pytest housekeeping | `0e1b802` |
| M3 — Adapter Readiness & First Real Run | E3.1–E3.2 (2) | `--context` CLI flag (CONTRACT §7); first real agentic run, accepted on independently-verified cross-repo evidence (ai-project-system P7-M26) | `282b18f` |

5 epics across 2 milestones. 209 passed / 1 skipped (offline suite on `phase/P2`).

**Step 2 — Phase completion criteria verified** (Phase spec
`docs/phases/P2__phase__first-real-run.md`):
- ✅ All milestones under P2 completed and closed (table above)
- ✅ **The first REAL agentic run succeeded:** a live Epic executed through
  ai-project-system's orchestrator with this runner as `dev_command`, non-mocked,
  converging on attempt 1 of 3, accepted in its parent Milestone Chat (P2-M3) — the
  project Brief's success criterion (CFO-confirmed, Creation Chat 2026-07-10). Evidence
  independently re-verified by this Phase Chat before acceptance (see
  `P2-M3__closure-declaration.md` for the full verification record), not trusted from the
  cross-repo hand-back's claims alone.

**Step 3 — README updated** (`c6ee545`): delivered-state banner, capability summary
(full coding toolset, `--context`, SN-3 nudge, the first real run), test count (209/1).

**Step 4 — Version bumped** (`c6ee545`): `pyproject.toml` `1.0.0` → `2.0.0`
(phase-id-as-major, per the P1 precedent: phase 1 closed as `v1.0.0`).

`phase/P2` HEAD at Stage 1: `c6ee545`. Working tree clean; full suite green.

---

## Process Record

- **SN-4 cross-repo hold and resolution:** P2-M3/E3.2 was held pending ai-project-system's
  own adapter Epic (SN-4). Full chain, each artifact `status: resolved`:
  `P2__escalation-notice__m3-e3-2-sn-4-blocked.md` (Phase Chat → HQ),
  `P2-M3__escalation-notice__e3-2-sn-4-blocked.md` (Milestone → Phase, closed the loop),
  the ai-project-system HQ Ruling
  (`ai-project-system/.ai-project/artifacts/rulings/2026-07-11__ai-project-system-hq__ruling__p7-ae-1-adapter-unblocks-runner-p2.md`),
  and the cross-repo hand-back
  (`ai-project-system/docs/phases/P7__Agentic_Execution_and_Default_On_Visuals/P7-M26__escalation-notice__cross-repo-hand-back-p2-m3.md`).
- **A real, independently-confirmed non-issue:** the cross-repo evidence surfaced an
  `allow_paths` glob bug during the live run. Verified by direct inspection of
  `local_agent_runner/tools.py`'s `path_permitted()` that the defect is a bad glob value in
  ai-project-system's own `.ai-project/agents/tools.json`, not this repo's code — CONTRACT
  §4's own example glob is already absolute-style (`/repo/**`), matching documented
  behavior exactly. No follow-up needed in this repository.
- **Acceptance model:** SN-13 default-accept throughout — both Milestones' deliveries were
  clean (Definition of Done, acceptance criteria, and spec all met, independently
  re-verified before each merge); no Review Decision artifact was required for either.

---

## What P2 Delivered (pending consolidation to `master`)

- The full CONTRACT §4 coding toolset: `write_file`, `list_dir`, `git`, with `allow_paths`
  enforced uniformly across every file tool and `allow_subcommands` scoping `git`
- The SN-3 final-answer repair nudge — bounded to one corrective round, §5 deterministic
  termination untouched — and proven load-bearing, not merely cautious: the first real
  run's own `final_answer` was a boilerplate refusal on its converging attempt
- The `--context` CLI flag, closing the last CONTRACT §7 runner-side gap
- **The project's founding real-world proof:** a live, non-mocked Epic executed through
  ai-project-system's orchestrator with this runner as `dev_command`, converging on
  attempt 1 of 3 — the Brief's success criterion, met

---

## Carry-Forward to P3

| ID | Title | Priority |
|----|-------|----------|
| CF-2 | Library entry point `run(...) -> Result` with pluggable custom tool handlers | TBD — deferred by CFO decision in P2 |
| CF-4 | Broader hardening: multi-model validation, retry/backoff, concurrency, packaging | TBD |

---

## Stage 2: Consolidation to `main` — PERFORMED BY HQ CHAT

Per `governance/systems/roles-authorization-team-governance.md`'s "Merging to Branches"
table, `main` (this repo's production branch; the table's generic "master" row) merges
require explicit CFO authorization — performed here by HQ Chat under that authorization,
not by the Phase Chat.

- [x] Review of Stage 1 (this document) and the Phase spec's completion criteria — HQ
      independently re-verified: full offline suite re-run post-merge (209 passed / 1
      skipped, matching Stage 1's count exactly), and a direct grep of
      `local_agent_runner/` confirmed no `subprocess` call ever shells out to the `ollama`
      CLI (CONTRACT §1 invariant #1 holds).
- [x] PSG §5C Step 5 — consolidated `phase/P2` → `main` via local no-ff merge (no hosted
      remote exists to open a PR against): merge commit `367bd23`.
- [x] PSG §5C Step 8 — tagged the closure commit `v2.0.0`.
- [x] PSG §5C Step 9 — frontmatter above records `merge_commit`, `tag`,
      `main_head_at_closure`, `closed_date`, `closed_by`, and `acceptance_model`; sign-off
      below.

## Sign-Off

Phase P2 is closed. At `v2.0.0` the runner carries the full CONTRACT §4 coding toolset, a
bounded final-answer repair nudge proven load-bearing on a real run, and closes the last
CONTRACT §7 runner-side gap (`--context`). The project's founding claim is no longer a
proof-of-concept result: a live, non-mocked Epic ran through ai-project-system's own
orchestrator with this engine as `dev_command` and converged on the first attempt. What
remains (CF-2, CF-4) is deferred scope and hardening on top of a runner now proven in
production use, not open questions about whether the approach works.
