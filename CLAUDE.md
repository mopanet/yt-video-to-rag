# video-to-rag

Risk-tiered, two-gate workflow — gstack + OpenSpec (T2) + TDD.
**Full dev guide:** `.dev/guide.md` (imported below).

@.dev/guide.md

## Essentials (full detail in `.dev/guide.md`)
- **Tier first:** classify every task **T0/T1/T2** (escalation rule in the guide) and **state the
  tier** at the top of your plan. T1 is the default; when unsure, escalate one tier.
- **Clean tree before any work:** run `npm run preflight`; if dirty, commit/`git stash`/`git restore` first. (`new-feature` enforces the same gate on the host.)
- **GATE 1 (you):** approve the plan before any code — T1: short plan (inline is fine); T2: OpenSpec `proposal.md`. Skipped only for T0.
- **Autonomous between gates:** build (tests) → **`npm run gates:dev`** (lint + **affected tests only**, fast) → review (T1: `/review` only; T2: `/review` + `/codex` + `/cso`) → ship.
  The **full** `npm run gates` (all tests + coverage + build) runs **only at the base-branch merge** (and in CI) — never on every slice.
  Self-heals ≤3 rounds; security findings & scope-creep (T1 outgrowing its tier) escalate to you immediately.
- **GATE 2 (you, T2/production only):** approve go-live → `/land-and-deploy` + `/canary`.
- **Releases:** CHANGELOG + version bump at release time, not per slice.
- **Plans:** every plan/design doc (`/office-hours`, `/plan-*-review`, PRDs) **always** goes in `.dev/plans/` — never the repo root.
- **SoT:** OpenSpec (`openspec/specs/`) + git = engineering; Linear = tracking only.
- You never run npm/git/tests by hand — the pipeline does.

## Model selection — delegate to Sonnet subagents (Claude Code only)
The main-loop model can't downgrade itself mid-session, but it **can offload cheap, well-scoped
work to a Sonnet subagent** via the `Agent` tool (`model: "sonnet"`). Prefer this to keep the
expensive model on the hard parts:
- **Delegate to Sonnet** (`Agent`, `model: "sonnet"`): file/symbol search, mechanical refactors,
  boilerplate/scaffolding, running & summarizing tests, doc/comment edits, format-only changes.
- **Keep on the main model:** architecture & design, spec/proposal shaping, `/review` `/codex`
  `/cso` judgement, security reasoning, anything touching a GATE.
- Only delegate when the task is **self-contained** (clear inputs, verifiable output) — hand the
  subagent enough context that it needn't ask back. When unsure, don't delegate.
- Codex ignores this section (it reads `AGENTS.md` → `.dev/guide.md`, not this file).
