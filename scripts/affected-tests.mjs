#!/usr/bin/env node
// affected-tests.mjs — print the test files affected by the current change set.
//
// Used by `npm run test:affected` / `npm run gates:dev` so day-to-day work runs
// ONLY the relevant tests. The full suite (coverage floor, build) runs at the
// integration point — merging into the base branch — not on every small change.
//
// Change set (default): staged + unstaged + untracked working-tree files — i.e.
// what you are editing right now, so day-to-day runs stay tight. Set
// AFFECTED_SCOPE=branch to also include everything committed on this branch since
// the integration base (merge-base with origin/<base>, then <base>).
//
// Mapping (precise, import-based — a test is "affected" when it imports a changed
// source file, resolved to an absolute path so same-named files don't collide):
//   • a changed test file (**/*.test.{js,mjs,ts})            → itself
//   • a changed source file                                   → every test that
//     imports it DIRECTLY
// Direct-import keeps the dev run tight and predictable; the transitive blast
// radius of a deep change is covered by the full suite at the dev merge.
//
// Prints affected test paths, one per line (empty output = nothing to run).
// With --run, runs `node --test` on them (exit 0 when none).
// With --lint, runs `biome check` on the changed lintable files only.
// Override the base branch with BASE_BRANCH=main (default: dev, then main).
import { execSync, spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, extname, resolve } from 'node:path';

const TEST_RE = /\.test\.(js|mjs|ts|jsx|tsx)$/;
const SRC_RE = /\.(js|mjs|ts|jsx|tsx)$/;
const root = execSync('git rev-parse --show-toplevel').toString().trim();
const sh = (cmd) => {
  try {
    return execSync(cmd, { cwd: root }).toString();
  } catch {
    return '';
  }
};

// ---- change set (absolute paths) ----
const lines = (s) =>
  s
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean);
const sources = [
  sh('git diff --name-only'), // unstaged
  sh('git diff --name-only --cached'), // staged
  sh('git ls-files --others --exclude-standard'), // untracked
];
if (process.env.AFFECTED_SCOPE === 'branch') {
  // Only safe branch-name chars reach the shell (BASE_BRANCH is external input).
  const candidates = [process.env.BASE_BRANCH, 'dev', 'main'].filter(
    (b) => b && /^[A-Za-z0-9._/-]+$/.test(b),
  );
  let base = '';
  for (const b of candidates) {
    base =
      sh(`git merge-base HEAD origin/${b} 2>/dev/null`).trim() ||
      sh(`git merge-base HEAD ${b} 2>/dev/null`).trim();
    if (base) break;
  }
  if (base) sources.push(sh(`git diff --name-only ${base}...HEAD`));
}
const changed = new Set();
for (const rel of sources.flatMap(lines)) changed.add(resolve(root, rel));

// ---- index every test file and its imports ----
const allTests = lines(
  sh("git ls-files '*.test.js' '*.test.mjs' '*.test.ts' '*.test.jsx' '*.test.tsx'"),
).map((r) => resolve(root, r));
const allSrc = lines(sh("git ls-files 'src/*' 'app/*' 'lib/*' 'components/*'"))
  .map((r) => resolve(root, r))
  .filter((f) => SRC_RE.test(f));

const IMPORT_RE = /(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]/g;
function importsOf(file) {
  if (!existsSync(file)) return [];
  const out = [];
  for (const m of readFileSync(file, 'utf8').matchAll(IMPORT_RE)) {
    const spec = m[1] || m[2];
    if (!spec?.startsWith('.')) continue; // only local imports
    let p = resolve(dirname(file), spec);
    if (!extname(p)) {
      // resolve extensionless / index imports against known sources
      const hit = allSrc.find(
        (s) =>
          s === p ||
          s.startsWith(`${p}.`) ||
          s === resolve(p, 'index.js') ||
          s === resolve(p, 'index.ts'),
      );
      if (hit) p = hit;
    }
    out.push(p);
  }
  return out;
}

// ---- collect affected tests: changed test files + tests importing a changed source ----
const changedSources = new Set([...changed].filter((f) => SRC_RE.test(f) && !TEST_RE.test(f)));
const affected = new Set();
for (const f of changed) if (TEST_RE.test(f) && allTests.includes(f)) affected.add(f);
for (const t of allTests) {
  if (affected.has(t)) continue;
  if (importsOf(t).some((dep) => changedSources.has(dep))) affected.add(t);
}

// --lint: run biome only on the CHANGED lintable files (not the whole project),
// so the dev gate never fails on pre-existing issues in files you did not touch.
if (process.argv.includes('--lint')) {
  const lintFiles = [...changed].filter((f) => SRC_RE.test(f)).map((f) => f.slice(root.length + 1));
  if (!lintFiles.length) {
    console.error('affected-tests: no changed files to lint');
    process.exit(0);
  }
  const r = spawnSync('biome', ['check', ...lintFiles], { stdio: 'inherit', cwd: root });
  process.exit(r.status ?? 1);
}

const files = [...affected].sort().map((t) => t.slice(root.length + 1));
if (process.argv.includes('--run')) {
  if (!files.length) {
    console.error('affected-tests: no affected tests — nothing to run');
    process.exit(0);
  }
  console.error(`affected-tests: running ${files.length} test file(s)`);
  const r = spawnSync('node', ['--test', ...files], { stdio: 'inherit', cwd: root });
  process.exit(r.status ?? 1);
}
for (const f of files) process.stdout.write(`${f}\n`);
