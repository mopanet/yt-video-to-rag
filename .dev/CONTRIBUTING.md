# Contributing

This repo follows the risk-tiered, two-gate workflow (see `CLAUDE.md` and `.dev/guide.md`).

## Tiers (classify before any work; clean tree always)
- **T0 — trivial** (typo/docs/config, no behavior change): do it → tests green → commit.
- **T1 — small feature** (one session; the default):
  short plan → 👤 **GATE 1** (approve the plan) → build with tests → `npm run gates` →
  `/review` → commit + PR. No OpenSpec, no CHANGELOG/version bump.
- **T2 — large/risky** (multi-slice; data/auth/API; hard to reverse) — the full loop:
  1. `/opsx:propose "<idea>"` — spec (proposal + WHEN/THEN scenarios + tasks).
  2. 👤 **GATE 1** — approve the plan (not the code).
  3. TDD: every scenario → a failing test (RED) first, then minimal code (GREEN).
  4. Machine gates: `npm run gates`.
  5. `/review` + `/codex` + `/cso`, then `/ship` (CHANGELOG + version here).
  6. 👤 **GATE 2** — approve go-live, then `/land-and-deploy` + `/canary`.
  7. `/opsx:archive`.

**Escalation rule:** data model / auth / security / public API / multi-session / hard to
reverse → T2. When unsure, escalate one tier. A T1 that grows mid-build re-opens GATE 1 as T2.

## Rules
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- One slice = one branch = one PR. Protected `main`, no `develop`.
- Every behavior change gets a test before merge (T2: test-first, RED→GREEN).
