# video-to-rag

Built with the risk-tiered, two-gate agentic workflow (gstack + OpenSpec for large changes + TDD).
See `.dev/guide.md` for the full process (the root `CLAUDE.md` imports it). Engineering
source-of-truth: `openspec/`.

## How development works
Every task is tiered by risk: **T0** (trivial — just do it), **T1** (small feature — short plan,
you approve at **GATE 1**, build with tests, one review, PR) or **T2** (large/risky — full
OpenSpec loop with TDD, triple review and a **GATE 2** go-live approval). You never run
npm/git/tests by hand.

Toolchain: Python 3.12 via [uv](https://docs.astral.sh/uv/), pytest, Ruff; the npm scripts are
the task runner.

```bash
npm test          # run the scenario tests (pytest)
npm run gates     # Ruff check + test + secret-scan + openspec validate
```

Start a slice — T1 (default): just describe it; T2 (large/risky):
```text
/opsx:propose "<your idea>"
```
