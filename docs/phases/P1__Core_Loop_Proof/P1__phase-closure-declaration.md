---
type: phase-closure-declaration
phase: P1
name: Core Loop Proof
status: closed
merge_commit: ff7288a
tag: v1.0.0
main_head_at_closure: ff7288a
closed_date: 2026-07-10
closed_by: Phase Chat (P1); accepted by HQ Chat
acceptance_model: SN-13 default-accept — explicit HQ acceptance given in-session 2026-07-10; no Review Decision artifact required
---

# Phase P1 Closure Declaration

**Phase P1 — Core Loop Proof is closed.**

Merge commit `ff7288a` landed on `main`. Tagged `v1.0.0`.

---

## Delivery Record

| Milestone | Epics | Scope / gaps closed | PR | Merge commit |
|-----------|-------|---------------------|-----|--------------|
| M1 — First-Proof Milestone | E1.1–E1.5 (5) | Ollama HTTP client; native/content tool-call parser with schema coercion; three permission-scoped proof tools; §5 execution loop, §3 transcript, §2 CLI; the §9 proof (3/3 converging containerized runs) | n/a — local merge (no remote) | `24fee22` |

5 epics. 155 passed / 1 environment-conditional skip.

---

## Process Record

- Closure recorded under SN-13 default-accept (PSG §11.6); HQ Chat gave explicit
  in-session acceptance on 2026-07-10 after the Phase Chat's independent verification of
  the M1 Closure Declaration (suite re-run, transcripts inspected, `ollama`-CLI grep).
- **No-remote adaptation (recorded M1, applied at phase level):** this repo has no hosted
  remote, so §5C Step 5's consolidation PR is replaced by a local no-ff merge; the merge
  commit message carries the PR-equivalent summary. Tag `v1.0.0` is local (nothing to push).
- **Versioning decision:** first phase closure adopts the §5C phase-id-as-major convention —
  `0.1.0` → `1.0.0`.
- **Late-tracked inception artifacts:** `genesis.md`, the Phase spec, the phase starter,
  `docs/hq-chat-opener.md`, and the Creation Chat steering note were untracked until closure;
  escalated twice by the Phase Chat and committed under HQ authorization at Step 1
  (`7a0feda`). Future phases: HQ artifacts should be committed when issued.
- **Process note carried from M1 closure** (`P1-M1__closure-declaration.md`): issue Epic
  Delivery Authorizations *before* launching Coding Agents; M1's were recorded retroactively.
- **Steering note (Creation Chat, 2026-07-09):** SN-1/SN-2 target the governance framework
  repo, not this project; they remain open with framework HQ
  (`.ai-project/artifacts/steering-notes/`).

---

## What P1 Delivered to `main`

- A working, governance-agnostic tool-calling engine (`local_agent_runner/`): Ollama HTTP
  client (`/api/chat`, never the CLI), native-first/content-fallback tool-call parser with
  JSON-schema argument coercion, `read_file`/`edit_file`/`run_command` with permission
  scoping, and the repair-don't-crash execution loop with deterministic termination.
- The §2 CLI (`local-agent-runner`) with exit codes 0/2/3/4 and §3 Result transcripts
  including per-call `eval_count` and total token accounting.
- The answered founding question: `qwen2.5-coder:14b` over Ollama's HTTP API reliably drove
  the §9 read → edit → run-test task to convergence — three consecutive containerized runs,
  zero repair rounds, clean transcripts committed at `proof/artifacts/`. Cost baseline:
  3 iterations, 134–432 tokens, 3.5–13.3 s per run.
- A fully offline test suite (155 tests over recorded fixtures — no server, Docker, or GPU)
  plus the reusable proof harness (`proof/`), including a mechanical transcript checker.
- The complete P1 governance record: Milestone and Epic specs, starters, delivery notices,
  and closure declarations under `docs/phases/P1__Core_Loop_Proof/`.

---

## Carry-Forward to P2

| ID | Title | Priority |
|----|-------|----------|
| CF-1 | Remaining built-in tools (`write_file`, `list_dir`, `git`) and full §4 permission model | TBD — HQ ratifies P2 scope |
| CF-2 | Library entry point `run(...) -> Result` with pluggable custom tool handlers | TBD |
| CF-3 | Governance adapter `bin/run-dev-agent` (the framework-consumption shim, §7) | TBD |
| CF-4 | Hardening: multi-model validation, retry/backoff, concurrency, packaging | TBD |
| CF-5 | Process: issue Epic Delivery Authorizations before Coding-Agent launch | process note |

---

## Sign-Off

Phase P1 is closed. At `v1.0.0` the engine is real: the core model → tool → result loop
converges reproducibly on a live local model, and everything that remains is more tools and
hardening on top of a proven loop.
