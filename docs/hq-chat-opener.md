---
artifact_type: hq_chat_opener
artifact_version: 1.0
source: creation_chat
project_name: local-agent-runner
date: 2026-07-09
---

# HQ Chat Opener — local-agent-runner

<!-- Produced by the Creation Chat per seed.md Rule 4. Field set follows
     .governance/governance/systems/hq-chat.md §"Standard HQ Chat Opener (Recommended)". -->

## Project
- **Name:** local-agent-runner
- **Repository:** own git repo (`local-agent-runner/`), standalone — not nested inside ai-project-system
- **Description:** Standalone tool-calling loop engine for local (Ollama) models. Governance-agnostic as software; its development is governed.

## Governance versions in use
- **Framework:** AI Project System `5.1.0` (submodule at `.governance/`, ref `v5.1.0`)
- **Project contract:** CONTRACT.md v0.1 accepted; §10 decisions settled.
- **Genesis:** `genesis.md` at project root, `status: complete`.

## Current Phase
- **Phase 1 — Core Loop Proof** (defined in `genesis.md`; not yet planned in a Phase Chat).

## Intended Milestone(s)
- **M1 — First-proof milestone (CONTRACT §9):** build the Ollama HTTP client, the
  model→tool→result loop, the native/content tool-call parser, and three proof tools
  (`read_file`, `edit_file`, `run_command`); confirm `qwen2.5-coder:14b` converges a 3-step
  read → edit → run-test task with a clean transcript.

## Stack
- **Language:** Python — matches ai-project-system tooling; Ollama HTTP + JSON + subprocess needs no heavy framework.
- **Runtime dependency:** Ollama over HTTP (`/api/chat`) via Docker at `http://localhost:11434` — never the CLI.
- **Default model:** `qwen2.5-coder:14b`.
- **Containerization:** the runner always runs inside a container, even standalone (CONTRACT §10.3).

## Objectives (from Project Brief / genesis.md)
- A local model executes Epic-scoped work with manageable, well-scoped context, producing results consistent with a frontier model's.
- Fallback execution path when cloud/frontier token budgets are exhausted.
- Standalone engine consumed by the AI Project System via a thin `bin/run-dev-agent` adapter; usable by other projects too.
- **Success criterion:** an Epic run via Agentic Mode, executed by this runner, is accepted in its parent Milestone Chat — same bar as any other epic.

## Known constraints
- Coexists with a local ComfyUI setup on shared GPU/VRAM (RTX 5060 Ti, 16 GB) — one heavy consumer at a time.
- Ollama is Docker-only on this host; no `ollama` CLI.
- Solo project: Francisco Guzmán holds CFO, Phase Lead, and Contributor.

## Non-goals
- No governance awareness inside the engine; caller enables tools; no uninvited context injection; not a chat UI, queue, or daemon.

## Parked ideas (not committed)
- A future UI/product in the direction of OpenClaw, Hermes, or GooseAI — explicitly deferred.

## Immediate next actions for HQ
1. Ratify Phase 1 scope from `genesis.md` and issue the Phase Execution Chat Starter for **Core Loop Proof**.
2. Ensure the Phase Chat plans M1 strictly to CONTRACT §9 — everything beyond is later phases (more tools, hardening, the governance adapter).
