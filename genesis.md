---
type: genesis
project: local-agent-runner
created_by: Francisco Guzmán (Creation Chat)
date: 2026-07-09
phase_1_name: Core Loop Proof
status: complete
---

# Genesis — Local Agent Runner

## Project Brief

A standalone tool-calling engine that runs Epics from the AI Project System governance
framework against a local Ollama model. It exists because Epic-scoped work — by design —
doesn't need a huge context window, so it should be small enough for a local model to produce
results consistent enough to be accepted like frontier-model work. This saves cloud tokens on
epic-scoped execution and provides a fallback when frontier/cloud token budgets run out.

**Goal:** You can run an Epic via Agentic Mode, executed by this local runner, and it gets
accepted in its parent Milestone Chat under the current governance system — the same bar as
any other epic.

**Problem:** Frontier-model tokens are the expensive, limited resource in the AI Project
System's pipeline. Epic-level work is small and well-scoped enough that a local model,
reached over Ollama's HTTP API, should be able to do it reliably — saving frontier tokens for
planning layers and providing continuity when cloud budgets are exhausted. The open,
unresolved question this project rests on: whether a local model can reliably do tool calling
for arbitrary tasks in general, not just a narrow proof case.

**Initial Team:**

| Role | Person | Authority |
|------|--------|-----------|
| CFO | Francisco Guzmán | Phase scope, production authorization |
| Phase Lead | Francisco Guzmán | Milestone planning, Epic acceptance |
| Contributor | Francisco Guzmán | Epic implementation |

<!-- Solo project — one person holding all three roles, confirmed in Creation Chat. -->

## HQ Context Packet

- **Project:** local-agent-runner
- **Governance path:** `.governance/` (submodule, pinned `v5.1.0` per `.ai-project.yml`)
- **Phase 1 scope summary:** Prove the core model → tool → result loop converges end-to-end on
  a real task, per CONTRACT.md §9. Phase 1 does not cover the governance adapter
  (`bin/run-dev-agent`), the full built-in tool library beyond the three proof tools, or any
  UI — those are later work.
- **Key constraints:** Must coexist with a local ComfyUI setup on shared GPU/VRAM (RTX 5060 Ti,
  16 GB) — one heavy consumer at a time. Ollama is reached only over HTTP via its Docker
  container (`http://localhost:11434`); the `ollama` CLI is not available. Solo project,
  currently.
- **Architecture visual:** none — this is a CLI/engine product with no UI. A future
  UI in the direction of OpenClaw, Hermes, or GooseAI was raised and explicitly parked, not
  committed.

## Phase 1 Scope

**Name:** Core Loop Proof

**Goal:** Prove the tool-calling loop works end-to-end: give `qwen2.5-coder:14b` a 3-step task
(read a file, edit one line, run a test that checks the edit) with `read_file` + `edit_file` +
`run_command` enabled, and confirm the loop converges to a passing result with a clean
transcript (CONTRACT.md §9). Everything past this is more tools and hardening — scoped to
later phases.

**Milestone stubs:**

- M1: First-proof milestone — build the Ollama HTTP client, the model→tool→result loop, the
  native/content tool-call parser, and the three proof tools (`read_file`, `edit_file`,
  `run_command`); make the §9 read → edit → run-test task converge with a clean transcript.

## Creation Chat Decisions

- Project name confirmed: `local-agent-runner`
- Phase 1 scope accepted: yes — limited to the CONTRACT.md §9 first-proof milestone only; the
  governance adapter and further tooling are explicitly deferred to a later phase
- Team roles assigned: Francisco Guzmán holds CFO, Phase Lead, and Contributor (solo project)

## Next Step

Open a Phase Chat using
[`.governance/governance/templates/phase-execution-chat-starter.md`](.governance/governance/templates/phase-execution-chat-starter.md),
passing this committed `genesis.md` as the mandatory context packet. The Phase Chat consumes
the HQ Context Packet and Phase 1 Scope above to plan the M1 milestone in detail. Do not begin
any execution until the Phase Chat has produced and authorized milestone work.
