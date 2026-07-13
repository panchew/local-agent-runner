# Epic Execution Chat Starter — E9.9 (fixture)

**Epic:** E9.9 — Greeting Helper
**Phase:** P9 — Fixture Phase
**Milestone:** M9 — Fixture Milestone

## Context

The onboarding flow needs a small greeting helper. This excerpt is
intentionally scoped to just this epic's concern — no governance rulebook,
no sibling-epic detail — matching CONTRACT.md §6's token-discipline
invariant: the runner is handed only what this epic needs, nothing more.

## Goals

1. Add `greet(name)` to `src/greet.py`.
2. Raise `ValueError` for an empty or whitespace-only `name`.
3. Cover both cases with a passing test in `tests/test_greet.py`.
