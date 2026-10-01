# TODO

- [x] Milestone 0: Confirm project skeleton
  - [x] Keep Python CLI package exposed as `moon`.
  - [x] Confirm `uv`, `ruff`, `ty`, and test setup in `pyproject.toml`.
  - [x] Keep runtime dependencies minimal and standard-library-first.
  - [x] Keep `scripts/codex-usage` executable as bundled fallback.


- [x] Milestone 1: Docker/Pi RPC integration spike
  - [x] Verify Docker runner image starts and can run Pi RPC mode.
  - [x] Verify project root RW mount and basic unrelated host filesystem isolation.
  - [x] Verify user-global skill mounts are read-only and Moon workflow skills are available in the image.
  - [x] Verify persistent Pi session storage survives ephemeral container removal.
  - [x] Verify UID/GID behavior leaves sensible host file ownership.
  - [x] Verify read-only container root plus writable temp dirs works for Pi.
  - [x] Verify configured provider/model/thinking, `--approve`, and skills work in RPC mode.
  - [x] Verify `get_state` returns session ID/file and session can be reopened from a new container.
  - [x] Verify steering, `clear_queue`, and `abort` behavior.
  - [x] Verify narrow OpenAI Codex credential injection without mounting the full host Pi home.
  - [x] Verify container Git can edit/commit and Moon can measure HEAD/diff changes after exit.
  - [x] Record implementation constraints before building the full runner.

- [x] Milestone 2: Runner image baseline
  - [x] Create real runner Dockerfile at `docker/runner/Dockerfile`.
  - [x] Pin Pi version with `PI_VERSION=0.85.1`.
  - [x] Build local development image `moonlighter-runner:0.1.0-dev`.
  - [x] Create placeholder Moon workflow skills in repo-level `skills/`.
  - [x] Bundle Moon workflow skills into the runner image at `/opt/moon/skills/`.
  - [x] Document runner image build and runtime mount expectations.
  - [x] Validate Pi RPC starts from the runner image and Moon skills appear in `get_commands`.

- [x] Milestone 3: Config and validation
  - [x] Implement config loading from `~/.config/moon/config.toml`.
  - [x] Add bundled sample config defaults: one project root, OpenAI Codex provider/model, medium thinking, work windows, 25% reserve, 20-minute chunks.
  - [x] Implement `moon config init` without overwriting existing config.
  - [x] Implement `moon config check` with helpful human output.
  - [x] Reuse config validation programmatically in other commands.
  - [x] Validate supported provider, non-empty model, known thinking level, fallback usage script presence, and expected directories.

- [x] Milestone 4: Core project model
  - [x] Discover direct child directories under the single configured project root.
  - [x] Ignore bare files and nested subprojects.
  - [x] Define standard project initialization for `.moon/`.
  - [x] Create `.moon/brief.md` with placeholder text when missing.
  - [x] Create `.moon/status.md`, `.moon/state.json`, `.moon/agent-result.json` handling, and `.moon/logs/`.
  - [x] Initialize git when needed and add `.moon/` to project `.gitignore`.
  - [x] Do not create an initial git commit during initialization.
  - [x] Ensure `.moon/state.json` is Moon-owned and never directly edited by the Pi agent.
  - [x] Validate `.moon/state.json` without silent repair.
  - [x] Define and validate `.moon/agent-result.json` dispositions: `active`, `needs_direction`, `complete`, `tabled`.

- [x] Milestone 5: User-facing project commands
  - [x] Implement `moon init <project>`; create project directory if missing.
  - [x] Implement `moon claim <path>` by moving into the root, erroring on name conflicts, then initializing.
  - [x] Record the most recent claim source path in project metadata during `moon claim`.
  - [x] Implement `moon release <project> [dest]` by moving the whole directory unchanged, using explicit `dest` or the recorded claim source path.
  - [x] Error helpfully when release has no explicit destination and no recorded claim source path.
  - [x] Error helpfully when the release destination already exists.
  - [x] Implement `moon activate <project>`; initialize if needed, clear completion/tabled state, and clear project pause.
  - [x] Implement `moon pause`, `moon resume`, `moon pause <project>`, and `moon resume <project>`.
  - [x] Ensure `moon resume <project>` also clears completion/tabled state.

- [x] Milestone 6: Status reporting
  - [x] Implement read-only `moon status`.
  - [x] Implement read-only `moon status <project>`.
  - [x] Show global pause before work-hours info.
  - [x] Show current work/no-work state, time until change, and next work window when outside work hours.
  - [x] Show active, paused, completed/tabled, uninitialized, and needs-brief project sections.
  - [x] Show last-known budget near the bottom only; do not perform live budget checks.
  - [x] Keep global status concise with no recent run summaries by default.
  - [x] Show terse last 3 run summaries in `moon status <project>`.

- [x] Milestone 7: Schedule and budget gates
  - [x] Implement simple work-window scheduler using local system timezone.
  - [x] Support multiple windows, day names, `daily`, `weekdays`, `weekends`, overlapping windows, and overnight windows.
  - [x] Implement `codex-usage` provider: installed command first, bundled `scripts/codex-usage` fallback.
  - [x] Parse remaining 5-hour and weekly quota plus reset times.
  - [x] Store last-known budget in global status/state.
  - [x] Implement linear weekly budget curve with configurable reserve defaulting to 25%.
  - [x] Fail closed on unknown/failed budget checks: no project touches, update global status/log, exit zero.

- [x] Milestone 8: Moonlighter skills/prompts
  - [x] Create repo-level `skills/` directory for development.
  - [x] Add work-chunk skill for automatic Pi project work.
  - [x] Add chunk-summary skill for wrap-up/status/log updates.
  - [x] Add brief-update skill/workflow for updating `.moon/brief.md`, especially after grill-me sessions.
  - [x] Ensure Moon workflow skills are bundled into the runner image.
  - [x] Document explicit human usage with `pi --skill ...`.
  - [x] Ensure runner explicitly loads/invokes Moon workflow skills.

- [x] Milestone 9: Dockerized Pi RPC runner MVP
  - [x] Build/use official versioned Moon runner image containing Pi, Moon skills, Git, Bash, and baseline utilities.
  - [x] Pin the runner image version expected by the Moon release.
  - [x] Implement host-side Docker orchestration for ephemeral runner containers.
  - [x] Mount project root RW, user-global Pi skills RO, and persistent Pi session storage RW.
  - [x] Avoid broad host-home, SSH, Moon config/runtime, Docker socket, and privileged mounts.
  - [x] Run Pi in RPC mode with `--approve`, configured provider/model/thinking, and Moon workflow skills.
  - [x] Store best-effort per-project Pi session ID and session file/path in `.moon/state.json`.
  - [x] Prefer useful Pi session names including project name when supported.
  - [x] Run configurable work chunks, defaulting to 20 minutes.
  - [x] Implement cooperative soft deadline plus RPC `clear_queue`/`abort`; kill container only as watchdog fallback.
  - [x] Consume `.moon/agent-result.json`; Moon updates `.moon/state.json`.
  - [x] Validate `.moon/state.json` after each chunk and fail/log if invalid.

- [x] Milestone 10: Manual `moon tick` end-to-end MVP
  - [x] Make `moon tick` silent unless errors.
  - [x] Validate config and project root before running.
  - [x] Respect global pause, work hours, and budget before touching projects.
  - [x] Initialize all uninitialized projects only after work-hours and budget checks pass.
  - [x] Select uninitialized projects first, randomly among them; otherwise round-robin by last-run time.
  - [x] Skip paused and completed/tabled projects.
  - [x] Let Pi agent decide whether sufficient direction exists from `.moon/brief.md` or project files.
  - [x] Treat `needs_direction`, `complete`, and `tabled` projects as out of ordinary autonomous rotation.
  - [x] Re-check work hours and budget between chunks.
  - [x] Support multiple projects per tick, rotating after chunks if time/budget remain.
  - [x] Treat usage/budget skips as expected zero-exit outcomes.
  - [x] Exit nonzero for invalid/missing config, missing project root, internal crashes, and runner failures when no later project succeeds.

- [x] Milestone 11: Git automation and logs
  - [x] In runner instructions, require frequent commits at coherent task boundaries.
  - [x] Require high-quality commit messages.
  - [x] Best-effort run obvious relevant tests before commits when practical.
  - [x] Never push automatically in v1.
  - [x] Allow work with uncommitted changes and merge conflicts; agent should inspect/continue/resolve.
  - [x] Write project summaries under `.moon/logs/` without full runner stdout/stderr.
  - [x] Write terse global tick summaries under `~/.local/state/moon/logs/` plus warnings/errors.
  - [x] Include operational metrics such as elapsed time, token usage deltas when available, commit count, and git-style line deltas.

- [ ] QoL / pre-systemd polish
  - [ ] Refresh stale budget data for `moon status` when last-known budget is older than a configured freshness threshold.
  - [ ] Show when budget was last checked in `moon status`.
  - [ ] Avoid showing week-old budget data as if current; mark stale data clearly if live refresh fails.
  - [ ] Replace/augment `moon-time-left` with `moon-should-continue` helper inside runner containers.
  - [ ] Generate a per-chunk control policy file containing deadline, wrap/urgent thresholds, and budget-pressure level.
  - [ ] Make `moon-should-continue` emit terse directives: `OK`, `wrap-up`, `record-and-end`, or `end-urgently`.
  - [ ] Update Moon workflow skills so agents call `moon-should-continue` after each meaningful action/checkpoint and obey the directive.
  - [ ] Keep project disposition decisions independent: agents may still mark `complete`, `needs_direction`, or `tabled` before chunk time expires.
  - [ ] Keep host-side budget checks authoritative before/between chunks; helper only provides in-chunk guidance based on precomputed pressure.
  - [ ] Add tests for helper threshold behavior and skill references.

- [ ] Milestone 12: MVP validation pass
  - [ ] Add unit tests for config parsing/validation.
  - [ ] Add unit tests for work-window scheduling.
  - [ ] Add unit tests for budget parsing and weekly curve math.
  - [ ] Add unit tests for project discovery/state/status classification.
  - [ ] Add integration-style tests for command flows using temporary directories.
  - [ ] Run `uv run ruff format .`.
  - [ ] Run `uv run ruff check .`.
  - [ ] Run `uv run ty check`.
  - [ ] Run tests.

- [ ] Post-MVP: immediately after manual tick works
  - [ ] Add `moon setup` or equivalent setup flow for Docker access, runner image, project root, session storage, credential injection, and smoke testing.
  - [ ] Add systemd service/timer setup flow.
  - [ ] Add configurable timer interval defaulting to 30 minutes.
  - [ ] Consider editor command for `.moon/brief.md`.
  - [ ] Consider `moon skills install` or Pi package distribution.
  - [ ] Consider Pi per-session usage accounting.
  - [ ] Revisit resumable-session behavior after real-world work.
  - [ ] Revisit project selection beyond last-run round-robin.
  - [ ] Revisit timed pauses for v2.
