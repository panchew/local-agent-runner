---
artifact_type: steering_note
artifact_version: 1.0
timestamp: 2026-07-09T00:00:00Z
issuer_chat: Creation Chat (local-agent-runner)
target: HQ Chat (ai-project-system — framework governance)
project_name: local-agent-runner
concerns:
  - id: SN-1
    severity: medium
    title: Level-0 handoff is defined two different ways (seed.md vs genesis.md flow)
  - id: SN-2
    severity: low
    title: No HQ Chat starter template exists, though every other level has one
---

# Steering Note — Creation Chat to HQ Chat (framework)

## Purpose

Closes the local-agent-runner inception session. During inception, the Creation Chat had to
reconcile two conflicting definitions of its own convergence target inside governance v5.1.0.
This note hands the inconsistency to the framework's HQ for a governance fix; the
local-agent-runner project itself is unblocked (it produced both artifacts).

---

## Concerns for HQ Triage

### SN-1 — Level-0 handoff is defined two different ways [MEDIUM]

**Detail:** `governance/templates/seed.md` (Rule 4) defines the Creation Chat's convergence
target as two artifacts — a **Project Brief + an HQ Chat Opener** — and says the human carries
decisions "into the HQ Chat." But `governance/templates/genesis.md`,
`governance/systems/start-a-project.md` (Step 3), and `governance/systems/chat-hierarchy.md`
(Level 0) define the sole required artifact as a committed **`genesis.md`** whose "Next Step"
opens a **Phase Chat directly** — the HQ Chat is never opened in that flow, even though the
packet inside genesis.md is named "HQ Context Packet," and chat-hierarchy.md states Phase
Execution Chat Starters are issued *by HQ mode*. The `hq-chat.md` system doc independently
confirms the HQ Chat Opener as a real artifact ("Standard HQ Chat Opener (Recommended)"), so
the two flows are each internally supported but mutually contradictory at the handoff point.

**Required action:** Decide the canonical Level-0 output — (a) genesis.md only, with the HQ
Chat absorbed into bootstrap, or (b) genesis.md + HQ Chat Opener, with the HQ Chat as the
explicit next stop — and amend seed.md, genesis.md's Next Step, start-a-project.md, and
chat-hierarchy.md to agree.

### SN-2 — No HQ Chat starter template exists [LOW]

**Detail:** `governance/templates/` contains `phase-execution-chat-starter.md`,
`milestone-execution-chat-starter.md`, and `epic-execution-chat-starter.md`, but no HQ
equivalent; chat-hierarchy.md's Level-1 row lists HQ's opening input as "(bootstrap)" with no
artifact. Meanwhile `hq-chat.md` describes a "Standard HQ Chat Opener" only as prose
recommendations.

**Required action:** If SN-1 resolves toward keeping the HQ Chat Opener, promote
`hq-chat.md`'s field list into a proper `hq-chat-starter.md` template alongside the other
three.

---

## Decisions Already Made

1. For local-agent-runner, the Creation Chat produced **both** artifacts: a committed-ready
   `genesis.md` (project root, `status: complete`) **and** `docs/hq-chat-opener.md` following
   hq-chat.md's Standard Opener field list. The project proceeds regardless of how SN-1 is
   resolved.

---

## Carry-Over Open Items

None.

---

## Next Action

HQ Chat (framework) should:
1. Triage SN-1 and pick the canonical Level-0 handoff.
2. Amend the four documents named in SN-1 so they agree.
3. If the HQ Chat Opener survives, create the missing starter template (SN-2).
