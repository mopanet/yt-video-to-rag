---
description: Open this project's devcontainer — checks Docker (installs or guides you if missing) and the Dev Containers CLI, then brings the container up and tells you how to get in
allowed-tools: Bash, AskUserQuestion
---

Open this project's isolated **devcontainer** so the agent can work with full autonomy safely
(the container is the boundary — Docker isolation keeps the host out of the blast radius).

Assume the user may be **new to Docker / devcontainers**. Before each step, say in one short line
what you're about to do. **Never silently install heavy software — confirm first.** Be friendly.

## 1. Check we're in a scaffolded project
```bash
echo "OS: $(uname -s) ($(uname -m))"
[ -f .devcontainer/devcontainer.json ] && echo "devcontainer: found" \
  || echo "WARN: no .devcontainer/ here — run this inside a project made by /new-project."
```
If there is no `.devcontainer/`, stop and tell the user.

## 2. Check Docker
```bash
if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 && echo "DOCKER: ready" || echo "DOCKER: installed but NOT running"
else
  echo "DOCKER: not installed"
fi
```
- **ready** → go to step 3.
- **installed but NOT running** → tell the user to start it, then re-run `/start`:
  - macOS: open **Docker Desktop** (Spotlight → "Docker"), wait for the whale icon to go steady.
  - Linux: `sudo systemctl start docker`.
  Then **stop** (they re-run `/start` once it's up).
- **not installed** → go to step 2a.

### 2a. Install Docker (confirm first)
Ask with **AskUserQuestion**: "Docker isn't installed — install it now?" → options: "Yes, install" / "No, I'll do it".
If **Yes**:
- **macOS**: if `command -v brew` exists → run `brew install --cask docker`. Otherwise point them to
  <https://www.docker.com/products/docker-desktop/> (download, drag Docker to Applications).
  Then tell them: **launch Docker Desktop once**, accept the license, wait until it's running, and re-run `/start`.
- **Linux**: the official convenience script (needs sudo): `curl -fsSL https://get.docker.com | sh`,
  then `sudo usermod -aG docker "$USER"` and re-login. Re-run `/start` afterwards.
If **No**: print the download link and stop.

## 3. Ensure the Dev Containers CLI
```bash
if command -v devcontainer >/dev/null 2>&1; then
  echo "devcontainer CLI: ok"
elif command -v npm >/dev/null 2>&1; then
  echo "installing @devcontainers/cli…"; npm i -g @devcontainers/cli && echo "installed"
else
  echo "NEED NODE: install Node.js 22+ (https://nodejs.org), then re-run /start"
fi
```
If npm is missing, stop and ask them to install Node.js first.

## 4. Bring the container up
Tell the user: the first run **pulls the shared base image and sets up the container firewall**
(outbound limited to an allowlist, inbound locked) — a minute or two; later runs are fast.
```bash
devup up
```
If `devup` is not on the PATH, the dev-template `install.sh` has not been run on this machine:
tell the user to run it (then `source` their shell rc) and fall back to
`devcontainer up --workspace-folder .` for now.

## 5. Hand off — how to get in
Print both options clearly:
- **Terminal (autonomous agent):** `devup claude` (or `devup codex`) — full-autonomy agent inside
  the container, safe and contained. Just a shell: `devup`.
  (Avoid `devcontainer exec` for interactive use: it allocates no TTY, so the agent's UI exits at once.)
- **VS Code / Cursor:** open the folder → Command Palette → **"Dev Containers: Reopen in Container"**.

Tell them to run `devup` in their terminal to open a shell and verify it. Do **not** start the autonomous agent yourself — bring the container up and hand off.
(Unattended runs are started only by the host's `dev-work` runner, from the approved `To Do` list.)
