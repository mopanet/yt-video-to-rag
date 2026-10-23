# .dev/plans — plan and design documents

This directory is the **permanent home of the project's plans**. Every plan and
design document **always** goes here — never in the repo root, in `src/`, or
scattered elsewhere.

## What goes here
- `/office-hours` idea and scope docs
- outputs of `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/plan-devex-review`
- PRDs, design docs, any plan artifact written by a gstack planning skill or the user

## What does NOT go here
- **OpenSpec proposals** — they are the engineering source-of-truth and live in `openspec/changes/…/proposal.md`.
- **Code, tests** — `src/`, `test/`.

`.dev/plans/` is the *thinking* layer (the loop's "Plan" phase); OpenSpec is the
*contract* layer (WHEN/THEN scenarios + tasks). The plan is born here, then
`/opsx:propose` pours the approved scope into a formal proposal.

## Convention
- One file = one plan. A descriptive kebab-case name, optionally with a date prefix:
  `2026-06-01-auth-redesign.md`.
- The plan is written before GATE 1; this is where the user approves the *plan*, not the code.
