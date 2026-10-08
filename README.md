# Moonlighter

Moonlighter is a command-line tool for spending otherwise-idle AI coding budget on your side projects while protecting your priority access.

You give Moonlighter a directory of projects and a work schedule. Each project gets a plain-English brief, a status file, and Moon-owned state under `.moon/`. When work is allowed, Moonlighter starts a Dockerized Pi/Codex runner, asks it to make useful progress, records the result, and stops when schedule or budget policy says to stop.

Moonlighter is intentionally conservative:

- It checks budget before work and refreshes usage after chunks.
- It respects configured work windows for scheduled work.
- It runs automatic work in an ephemeral Docker container.
- It does not push commits.
- It keeps human guidance in `.moon/brief.md` and machine state in `.moon/state.json`.

Current status: early MVP. Manual runs, Dockerized work chunks, and user-level systemd timer setup are functional.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Docker access for the current user
- Authenticated `pi` CLI with OpenAI Codex access
- Local Moonlighter runner image

Build the runner image:

```bash
docker build -t moonlighter-runner:0.1.0-dev -f docker/runner/Dockerfile .
```

Install from a local checkout:

```bash
uv tool install .
```

For development:

```bash
uv sync --dev
uv run moon --help
```

## First-time setup

Create config:

```bash
moon config init
```

Edit it:

```bash
$EDITOR ~/.config/moon/config.toml
```

Check it:

```bash
moon config check
```

The config defines the Moon project root, work windows, runner image, model/provider settings, chunk duration, and budget reserve.

## Basic workflow

### 1. Create a project

```bash
moon init hydro-helper
```

This creates:

```text
<project-root>/hydro-helper/
  .moon/brief.md
  .moon/status.md
  .moon/state.json
  .moon/logs/
```

If `$EDITOR` is set, Moon opens `.moon/brief.md` immediately. Write what the project is, what success looks like, constraints, and useful next directions.

You can edit the brief later with:

```bash
moon brief hydro-helper
```

### 2. Check status

```bash
moon status
moon status hydro-helper
```

Global status shows schedule state, systemd service/timer state, runner state, active projects grouped by priority, project categories, and last-known budget. Project status shows disposition, pause state, priority, session metadata, requested feedback, and recent summaries.

### 3. Prioritize work

Projects default to `normal` priority. Set a higher or lower tier when some projects should be completed before others:

```bash
moon priority hydro-helper urgent
moon priority docs-refresh low
moon priority
```

Scheduled work scans active projects from highest priority to lowest: `urgent`, `high`, `normal`, `low`, then `backlog`.

### 4. Run one manual chunk

```bash
moon run hydro-helper
```

`moon run` starts one immediate work chunk. It ignores the work schedule but still respects the budget by default.

Useful variants:

```bash
moon run hydro-helper --chunk-minutes 10
moon run hydro-helper --ignore-budget
```

### 5. Respond to feedback

A missing or placeholder brief does not by itself remove a project from Active. For claimed/imported repositories, `moon status` labels the project `repo-guided`; the runner inspects repository context such as README, TODO, docs, tests, and package metadata before deciding whether it can proceed.

If the agent needs direction after inspecting available context, the project moves out of Active and into Needs Direction.

```bash
moon status hydro-helper
```

The status output shows the feedback request and suggests:

```bash
moon brief hydro-helper
```

Edit `.moon/brief.md` with your answer, then reactivate the project:

```bash
moon activate hydro-helper
```

### 6. Pause, resume, deactivate, reactivate

Pause all work:

```bash
moon pause
```

Resume all work:

```bash
moon resume
```

Pause one project:

```bash
moon pause hydro-helper
```

Resume/reactivate one project:

```bash
moon resume hydro-helper
```

`moon activate <project>` also clears completed/tabled state and project pause state.

### 7. Scheduled work entry point

```bash
moon work
```

`moon work` is the schedule-aware entry point intended for timers/services. It checks global pause, work windows, budget, and project eligibility. If work is not allowed, it exits quickly. If work is allowed, it runs chunks while schedule and budget gates allow.

Use `moon service` to install and manage a user-level systemd timer that invokes `moon work` periodically.

### 8. Optional systemd timer

Preview generated user systemd units without writing files:

```bash
moon service print
```

Install Moon-managed units under `~/.config/systemd/user/`:

```bash
moon service install
```

Enable and start the timer:

```bash
moon service enable
```

Check timer status and recent run history:

```bash
moon service status
moon status
moon log
```

Disable or remove the timer:

```bash
moon service disable
moon service uninstall
```

Moon uses user-level systemd only. It does not require `sudo` and does not write to `/etc/systemd/system`.

## Project lifecycle commands

### Create a new Moon-owned project

```bash
moon init my-project
```

Creates the project directory if missing, initializes `.moon/`, initializes Git if needed, adds `.moon/` to `.gitignore`, and opens the brief when `$EDITOR` is set.

### Claim an existing project

```bash
moon claim ~/code/existing-project
```

Moves the project into the configured Moon project root, initializes `.moon/` if needed, and records where it was claimed from. Claimed projects remain active even if the generated brief is still a placeholder; `moon status` labels them `repo-guided`, and the runner inspects repository context before asking for direction.

### Release a project

Release to the recorded claim source:

```bash
moon release existing-project
```

Release to an explicit destination:

```bash
moon release existing-project ~/code/existing-project
```

Release into an existing parent directory:

```bash
moon release moon-lighter-feedback-skill ~/.agents/skills/
```

If `~/.agents/skills/` exists, Moon releases to:

```text
~/.agents/skills/moon-lighter-feedback-skill
```

Moon refuses to overwrite existing destinations.

## Command reference

### `moon config init`

Create a sample config at `~/.config/moon/config.toml` if one does not already exist.

### `moon config check`

Validate config, project root, supported provider/model settings, runner image availability, Docker availability, and bundled budget fallback.

### `moon init <project>`

Create or initialize a project under the configured project root. Opens `.moon/brief.md` in `$EDITOR` when set.

### `moon brief <project>`

Open the project brief in `$EDITOR`.

### `moon status [project]`

Show global or per-project status. Global status groups active projects by priority tier.

Options:

```bash
moon status --color auto
moon status --color always
moon status --color never
```

### `moon priority [project] [priority]`

View or set project priority.

With no arguments, list initialized projects by priority tier:

```bash
moon priority
```

With a project only, show that project's priority:

```bash
moon priority hydro-helper
```

With a project and tier, set priority:

```bash
moon priority hydro-helper urgent
moon priority hydro-helper normal
```

Priority must be one of: `urgent`, `high`, `normal`, `low`, `backlog`.

### `moon log`

Show recent Moonlighter run history from `~/.local/state/moon/runs.jsonl`.

Examples:

```bash
moon log
moon log --limit 50
moon log --project hydro-helper
moon log --status skipped
```

The v1 history records when `moon run` / `moon work` started and ended, elapsed time, trigger (`manual` or `systemd`), projects run, status, skip reason, error, disposition, and chunk counts. Token and usage deltas are planned later.

### `moon run [project]`

Run one immediate manual work chunk. Ignores schedule/pause gates but respects budget unless `--ignore-budget` is provided.

Options:

```bash
moon run [project] --chunk-minutes 10
moon run [project] --ignore-budget
```

### `moon work`

Run scheduled work if allowed. Intended as the systemd/timer entry point.

Compatibility/debug options currently available:

```bash
moon work --force
moon work --force --ignore-budget
moon work --project <project>
moon work --minutes 10
```

`moon light` is a hidden alias for `moon work`.

### `moon service <command>`

Manage Moonlighter's user-level systemd service and timer. Managed files are:

```text
~/.config/systemd/user/moon.service
~/.config/systemd/user/moon.timer
```

Commands:

```bash
moon service print
moon service install
moon service enable
moon service status
moon service disable
moon service uninstall
```

Useful options:

```bash
moon service print --unit service
moon service print --unit timer
moon service install --print
moon service install --interval 5m
moon service install --moon /absolute/path/to/moon
```

`install` writes unit files but does not enable/start the timer. `enable` runs `systemctl --user enable --now moon.timer`. Moon refuses to overwrite or remove existing unit files unless they contain Moonlighter's managed-file header. The generated service sets `MOON_TRIGGER=systemd` so `moon log` can distinguish timer runs from manual runs.

### `moon pause [project]`

Pause all work, or pause one project.

### `moon resume [project]`

Resume all work, or resume/reactivate one project.

### `moon activate <project>`

Initialize if needed, clear project pause, and clear completed/tabled disposition.

### `moon claim <path>`

Move an existing directory into the configured project root and initialize it for Moon.

### `moon release <project> [dest]`

Move a project out of Moon control. If `dest` is omitted, Moon uses the recorded claim source path. If `dest` is an existing directory, Moon places the project inside it as a subdirectory. Existing destinations are never overwritten.

### `moon completion <shell>`

Print shell completion code for `bash`, `zsh`, or `fish`.

### `moon setup completion`

Install a managed completion block into your shell startup file.

Examples:

```bash
moon setup completion --shell bash --yes
moon setup completion --print
```

## Files Moon creates in projects

```text
.moon/brief.md          user/project guidance
.moon/status.md         human-readable handoff/status
.moon/state.json        Moon-owned machine state
.moon/agent-result.json agent-to-Moon handoff, when present
.moon/logs/             project run summaries
```

`.moon/state.json` is Moon-owned. Agents must not edit it directly. Agents request disposition changes by writing `.moon/agent-result.json`.

Project priority defaults to `normal`. Active project selection prefers higher priority tiers first, then falls back to the existing oldest-last-run rotation within the tier.

A real brief is recommended, but not required for claimed repositories that already contain clear project context. Placeholder briefs are shown as `repo-guided` status annotations, not blockers.

Common dispositions:

- `active`: autonomous work can continue
- `needs_direction`: user feedback is needed
- `complete`: goals appear met
- `tabled`: project should be skipped for now

## Budget and safety model

Moonlighter uses `codex-usage` to check Codex/Pi usage. An installed `codex-usage` command is preferred; a bundled fallback is included.

Budget behavior:

- Scheduled work fails closed when budget cannot be checked.
- Manual `moon run` respects budget unless `--ignore-budget` is used.
- Budget is refreshed after chunks so `moon status` reflects recent usage.
- The weekly budget curve reaches the configured reserve by the final 24 hours before reset.

Runner behavior:

- Pi runs in Docker RPC mode.
- Project workspace is mounted read/write.
- User global skills are mounted read-only when present.
- Moon workflow skills are bundled into the runner image.
- Pi sessions are persisted outside ephemeral containers.
- The systemd timer invokes plain `moon work`; it does not bypass schedule, pause, or budget gates.
- The agent is instructed to commit coherent completed work and never push.

## Shell completion

One-time setup:

```bash
moon setup completion --shell bash --yes
```

Or print completion code manually:

```bash
moon completion bash
moon completion zsh
moon completion fish
```

## More documentation

- `docs/runner/docker.md` — runner image/runtime notes
- `docs/skills.md` — bundled Moon workflow skills
- `docs/spikes/docker-pi-rpc.md` — Docker/Pi RPC feasibility notes
