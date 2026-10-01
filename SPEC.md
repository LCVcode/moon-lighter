# SPEC

## Overview

`moonlighter` is a Python CLI tool, exposed as `moon`, that periodically uses otherwise-unused weekly AI token budget to advance side projects. The v1 MVP should make manual `moon tick` work end-to-end first. Systemd/timer support should come immediately after, enabling unattended runs while preserving the user's priority access to tokens.

The initial target is Pi using OpenAI Codex models. Future versions may support additional providers and runners.

## Goals

- Watch a weekly token budget and only spend safe surplus.
- Run automatic off-hours work on projects in configured moon-owned project roots.
- Let users create new projects by making a directory and writing a plain-English `.moon/brief.md` brief.
- Keep users' priority token access protected through conservative budget gating and pause controls.
- Provide status commands showing global/project state and recent project milestones.
- Support moving projects out of and back into moon control.

## Non-goals

- Aggressively consuming all available tokens.
- Running project work when budget status is unknown.
- Supporting every provider in v1.
- Fully deciding the long-term project progression strategy in the initial spec.
- Requiring pristine git working trees before automatic work.

## Users / Use Cases

- A user has weekly Pi/Codex tokens that may otherwise expire unused.
- The user creates project directories under known roots such as ideas/concepts/projects directories.
- The user writes a `.moon/brief.md` brain dump and lets `moon` periodically improve the project.
- The user checks `moon status` to see overall state, project state, and recent milestones.
- The user pauses or resumes all work or individual projects. Timed pauses are deferred to v2.
- The user releases a project from moon control, then later claims it back if desired.

## Requirements

- Project name: `moonlighter`.
- CLI command: `moon`.
- Per-project brief file: `.moon/brief.md`.
- Global config path: `~/.config/moon/config.toml`.
- Implementation language: Python, with minimum practical dependencies.
- Packaging/install target: `uvx` / `uv tool install` style package.
- Use Python project defaults: `uv`, `ruff`, `ty`, tests, standard library first.
- Project discovery scans one configured project root directory for direct child project directories. Projects are not expected to contain nested subprojects. Bare files directly under the project root should be ignored.
- Uninitialized projects are direct child directories under the project root without `.moon/`.
- Uninitialized projects are eligible for work and should be prioritized over initialized projects; choose randomly among multiple uninitialized projects.
- `moon status` should be read-only and should never create `.moon/`.
- `moon status <project>` should also be read-only and report uninitialized projects without initializing them.
- `moon status` should show uninitialized project directories under an “uninitialized” section.
- Projects with placeholder-only `.moon/brief.md` should appear separately in status under “needs brief.”
- CLI project arguments should identify projects by directory name under the configured project root.
- Project name conflicts should be impossible in v1 because only one project root is configured.
- Projects inside the configured root are considered moon-owned workspaces.
- v1 project selection/rotation should be round-robin by last-run time.
- During a work window, moon may rotate among eligible projects after each chunk if budget and time remain.
- Project rotation strategy may change after v1.
- Automatic runs may continue with uncommitted changes; moon owns the workspace.
- If a project has uncommitted changes before an automatic run, the agent should inspect them and pick up where the last agent left off.
- Automatic work may run when the project has merge conflicts; the agent should try to resolve them.
- Moonlighter/runner should automatically commit frequently when a consistent task is completed.
- Git commits should have clear, high-quality commit messages.
- Commit timing should be task-boundary based, not mechanically tied to chunks or sessions.
- Before committing, the runner should make a best-effort attempt to run obvious relevant tests when practical.
- v1 should not enforce a maximum number of commits per run.
- On automatic-work failure, v1 should log the failure, update project/global status where appropriate, preserve the workspace for later continuation, and avoid destructive rollback unless explicitly safe.
- Runner failure classification is delegated to the agent. v1 should treat Pi CLI nonzero exit and missing required status/log handoff as runner failures. Test failures should be recorded as project context unless the runner itself cannot continue.
- v1 should never push commits to remotes automatically; this may change later.
- Every automatic run must update `.moon/status.md`, even if no code changes occur.
- Code changes are optional; a run may only update status.
- Completed projects should be marked in machine-readable project JSON state under `.moon/`, tabled, and skipped by default.
- Completion/tabled state should not be parsed from human-readable `.moon/status.md`.
- v1 should not include a user-facing manual complete command; users can pause or release/move projects instead.
- Users must be able to manually reactivate a completed/tabled project with `moon activate <project>`.
- `moon activate <project>` should work on uninitialized projects by initializing them, then setting completion/tabled state false and clearing project pause state.
- Activating an uninitialized project creates the placeholder `.moon/brief.md`; the brief may be empty/placeholder, but if the project is already started and does not need a brief, moon may proceed with further work.
- If the project `.moon/` machine state file is missing during activation, `moon activate <project>` should create it with completion/tabled state false.
- Users must be able to update project guidance and return the project to rotation.
- Updated guidance should primarily be detected from `.moon/brief.md` changes, but reactivation should remain manual.
- Moonlighter must provide v1 skills or agent workflows for work chunks, chunk summaries, and updating `.moon/brief.md`, especially after grill-me sessions.
- Moonlighter workflow skills should live in repo-level `skills/` during development and be bundled into the official runner image for v1 execution.
- Automatic Pi sessions should access Moon workflow skills via explicit skill invocation/loading from the runner image; user-global Pi skills should be mounted read-only and project-local skills trusted via `--approve`.
- Moon-generated Pi commands should pass `--approve`; moon owns its project workspaces.
- Moon-generated Pi runs must be headless and resumable via Pi RPC mode. Store Pi session ID and session file/path in `.moon/state.json` and prefer useful Pi session names including the project name when supported.
- For human interactive use in v1, document explicit `pi --skill ...` usage for moon skills.
- Commands such as `moon skills install` or packaging moon as a Pi package are deferred possibilities.
- The `.moon/brief.md` update workflow should primarily update `.moon/brief.md`; `moon status` should detect the changed guidance and report reactivation readiness rather than the workflow directly changing rotation state.
- `moon status` should show a summary.
- `moon status` should show whether it is currently work time or no-work time, and how long that state will last assuming no config changes.
- If currently outside work hours, `moon status` should show the next work window start time and duration.
- `moon status` should show last-known budget only, not perform a live budget check.
- Budget information should appear near the bottom of `moon status` and is relatively low importance.
- v1 should not include a separate live budget command.
- `moon status <project>` should show per-project detail.
- `moon release <project> [dest]` moves a project out of moon control.
- Release should move the whole project directory without modification, preserving `.moon/`.
- If `dest` is omitted, release should use the project's recorded most recent claim source path.
- `moon release` should error helpfully if `dest` is omitted and no recorded claim source path exists.
- `moon release` should error helpfully if the destination already exists.
- `moon claim <path>` brings a project under moon control by moving it into the configured project root.
- `moon claim` should record the source path the project was most recently claimed from in `.moon/state.json`.
- `moon claim` should error if a project with the same directory name already exists under the configured root.
- If a claimed project lacks `.moon/brief.md`, moon should create one during standard project initialization.
- A newly created `.moon/brief.md` should contain a short placeholder like “Replace me with a project concept/description.”
- `moon init <project>` should not accept initial brief text in v1; it creates the placeholder only.
- Consider adding a command like `moon edit <project>` or `moon brief <project>` to open `$EDITOR` for `.moon/brief.md`; this is nice-to-have and not blocking v1.
- Placeholder-only `.moon/brief.md` should not be the only signal for whether work can proceed.
- Moonlighter may proceed with work if the project has sufficient direction from the repository itself, such as TODO, SPEC, README, or similar files that make next steps clear.
- Moonlighter should require some kind of direction before work, but that direction can come from `.moon/brief.md` or from project files.
- Pi agent should decide whether a project has sufficient concrete direction to continue work, using an assessment/work prompt rather than pre-launch moon heuristics.
- If the Pi agent finds insufficient concrete direction, it should request `needs_direction` through `.moon/agent-result.json`; if no meaningful next work exists because stated goals are met, it may request `complete`.
- The Pi agent may request a disposition change without making code changes if appropriate, but completion requires positive evidence that goals are met.
- When requesting meaningful disposition changes, the agent must update `.moon/status.md` and write a project log summary explaining why.
- `.moon/state.json` is exclusively Moon-owned machine state; the Pi agent must not edit it directly.
- The Pi agent should communicate requested state/disposition changes through `.moon/agent-result.json`, which Moon validates and consumes.
- Moonlighter should validate `.moon/state.json` after each runner chunk; if invalid, fail/log rather than silently repairing.
- Moonlighter should provide a standard project initialization path that creates required `.moon/` structure/files.
- v1 should support `moon init <project>` for projects under the configured root; if the project directory is missing, `moon init <project>` should create it. `moon claim <path>` should also initialize after moving a project into the root.
- Support global and per-project pause/resume.
- v1 pause commands should be `moon pause`, `moon resume`, `moon pause <project>`, and `moon resume <project>`.
- v1 pause commands should not accept a reason/message; they only toggle paused/unpaused state.
- `moon resume <project>` should clear project pause and also reactivate a completed/tabled project by clearing completion state.
- Timed global and per-project pauses are deferred to v2.
- Initial runner should target Pi via a Dockerized runner using Pi RPC mode.
- Docker is the required v1 containment backend; other backends may come later.
- Moon remains the host-side control plane; autonomous Pi execution occurs inside ephemeral Docker containers.
- Moon should ship/version an official runner image containing Pi, Moon workflow skills, Git, Bash, common baseline utilities, and tested runtime dependencies.
- Initial local runner image baseline uses `docker/runner/Dockerfile`, pins Pi with `PI_VERSION=0.85.1`, and builds as `moonlighter-runner:0.1.0-dev`.
- Moon releases should pin/know their compatible runner image version rather than blindly using `latest`.
- A future/near-term `moon setup` flow should verify Docker access, project root, runner image availability, persistent Pi session storage, credential injection, user-global skill discovery, and a disposable smoke test.
- Pi model/provider for moon runs should be configured in `~/.config/moon/config.toml`, not left to Pi defaults.
- v1 config should require Pi provider, model, and thinking/reasoning level; only OpenAI/OpenAI Codex is supported for now.
- Configured thinking/reasoning level must be one of Pi's known values: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
- Sample config should default to OpenAI Codex with medium thinking/reasoning.
- `moon config check` should error if the configured provider is not supported by v1.
- Model-name validation is delegated to the agent; v1 should require a non-empty configured model and avoid live model-list checks during config validation.
- Token safety uses a time-aware budget curve.
- Automatic work should only run during configured moon work hours and when token-budget checks pass.
- Outside configured work hours, scheduled ticks must not touch project directories or project `.moon/status.md` files; they may update only global/log state. When globally paused, scheduled ticks must not touch project directories or initialize projects; they may update only global/log state.
- During work hours with insufficient budget, scheduled ticks must not touch project directories; they should update global/log state with the lack-of-budget reason.
- Work hours must support at least an every-day time window such as 02:00–04:00.
- v1 should support multiple work-hour windows per day using a simple scheduling system.
- Work-hour config should express days with day names such as `mon,tue,wed`.
- Work-hour config should also support simple day shorthands `daily`, `weekdays`, and `weekends` for convenience.
- Work-hour windows like `22:00-02:00` should be allowed and interpreted as crossing midnight.
- Overlapping work windows should be allowed; if any configured window matches, moon may run.
- Work-hours scheduling should use the local system timezone.
- Work hours should support a bare-bones weekday/weekend distinction if practical in v1.
- Work hours must be configurable via the CLI.
- Token source must be machine-readable. If budget status is unknown or usage checking fails, no automatic project work should run; `moon tick` should update global status/log and exit zero rather than treating it as a hard command error.
- Skipping work due to insufficient budget or usage-check failure is expected behavior.
- `moon tick` should exit nonzero for invalid/missing config, missing project root, internal crashes, and runner failures when no later project succeeds.
- If one project runner fails but another project succeeds in the same tick, `moon tick` may continue and exit zero; logs must show relevant warnings/errors.
- Budget source may be built into Pi usage support or supplied as a configured script/command.
- `codex-usage` is the preferred v1 command for tracking OpenAI Codex token usage.
- Keep a backup/reference copy of the current `codex-usage` script in `scripts/codex-usage`.
- The budget provider should try the installed `codex-usage` command first, then fall back to bundled `scripts/codex-usage`.
- Missing installed `codex-usage` should not be a config-check error as long as the bundled fallback script is available.
- `moon config check` should not call `codex-usage` or verify Pi/Codex auth; it should only care that the bundled fallback script is present.
- The `codex-usage` provider should parse/report remaining 5-hour and weekly quota plus reset times.
- Pi usage extension `npm:@tian.zuo/pi-usage` remains a possible budget source, but parseable non-interactive output must be verified.

## Constraints

- The user must retain a meaningful portion of weekly tokens for priority use.
- Weekly budget reserve should be configurable, defaulting to 25%.
- v1 should not enforce a separate 5-hour reserve before starting; it should use weekly budget curve plus work-hours gating only.
- During a running automatic session, token usage should be monitored repeatedly.
- If 5-hour tokens expire or weekly tokens fall below the active budget threshold mid-session, the runner should stop making code changes, update moon/status files with a summary, write logs, and exit cleanly.
- The tool must be pausable for long periods, though v1 pauses are untimed until manually resumed.
- v1 MVP should support manual `moon tick` end-to-end before systemd/timer automation.
- The first end-to-end manual `moon tick` MVP should include config, project init/discovery, budget check, resumable per-project Pi sessions, multi-project rotation in one tick, automatic commits, and status/log updates.
- Because Pi runner mechanics are uncertain, an early Docker/Pi RPC integration-validation spike should happen before the full runner milestone.
- Post-manual-tick backlog/phasing is delegated to the agent. Defer systemd/timer automation, interactive skill installation UX, advanced schedule/config commands, Pi per-session usage accounting, and richer project selection until after the first manual tick MVP.
- Automatic operation should fit systemd timer usage.
- The systemd timer wake interval should be configurable, defaulting to 30 minutes.
- Coupling to Pi/Codex internals should be minimized where practical.
- Budget provider and work runner should remain separable concepts.
- If no trustworthy budget source exists, fail closed.

## Design

### Configuration

Global config lives at `~/.config/moon/config.toml`. It should include the configured project root, budget provider settings, runner settings including Pi provider/model/thinking level, budget curve/reserve policy, work-hours configuration, and pause state or pointers to pause state. Config may be edited manually and/or bootstrapped on first run; exact setup UX remains flexible. If config is missing, moon should error with clear setup instructions rather than silently creating config. Moonlighter should provide a default/sample config that users can copy. v1 should provide `moon config init` to copy/write the sample config to `~/.config/moon/config.toml`. If an existing config is found, it should not overwrite; it should print the path and run/show config-check results. Config validation/linting should read the config and check sensible conditions such as whether expected directories exist. `moon config init` should not create the project root directory; the user must create it. `moon config check` should warn if the configured project root directory does not exist. For automatic `moon tick`, a missing project root is an error and should cause a nonzero exit. v1 should provide `moon config check` with helpful human output, and other commands should reuse the same validation functionality programmatically before running. Work-hours syntax should be minimal in v1, supporting multiple daily windows and preferably separate weekday/weekend windows.

Global runtime state should live under `~/.local/state/moon/`. Use `status.json` for latest status/reporting data, `state.json` for durable machine state such as global pause state, and `logs/` for global logs. Global logs should contain one very terse summary per tick plus warnings/errors. Tick summaries should focus on critical operational info such as time spent, token usage/spend, number of commits, and git-style line deltas like `+1234 -567`. Project-specific implementation details belong in that project's `.moon/` directory, not the global log.

Future versions may add environment variable overrides.

### Project model

A project is eligible when it is found under a configured project root and has been initialized with `.moon/brief.md`. Moonlighter may create a hidden `.moon/` directory containing human-readable status, Moon-owned machine-readable metadata, an agent-result channel, and logs. The initial mandatory human status file is `.moon/status.md`; project initialization should create it with a simple placeholder status. Project initialization should also create `.moon/logs/`. Per-project machine-readable state lives in `.moon/state.json`. It should be kept minimal in v1 and should not include a schema/version field. Completion/tabled/disposition state belongs in `.moon/state.json`, not in `status.md`. The Pi agent must not edit `.moon/state.json` directly; it requests state changes through `.moon/agent-result.json`, which Moon validates and consumes after chunks. Project `.moon/` directories should be ignored by git, including `.moon/brief.md`. When moon creates `.moon/`, it should automatically add `.moon/` to the project's `.gitignore`. If the moon-owned project is not yet a git repository, moon should initialize git and create/update `.gitignore` with `.moon/`, but should not create an initial commit during initialization. v1 state should include disposition, completion/tabled state as applicable, relevant timestamps, `.moon/brief.md` hash/change tracking, Pi session ID and session file/path, logs index, runner metadata as needed, most recent claim source path when applicable, and per-project pause state. Supported dispositions should include `active`, `needs_direction`, `complete`, and `tabled`; `needs_direction` is distinct from completion. `.moon/logs/` should store run summaries only, not full runner stdout/stderr. The exact summary format is delegated to the agent; Markdown summaries plus JSON metadata are preferred when useful. Per-project pause state should live only in that project's `.moon/state.json`. `moon status <project>` may read paused projects; project pause prevents automatic work, not status inspection. `moon tick` should skip paused projects silently; it should not mention paused project names in global status/log by default. `moon status` should show paused project names in a paused section.

Projects are moon-owned while under a configured root unless paused, `needs_direction`, complete, tabled, or otherwise excluded. Projects in `needs_direction`, `complete`, or `tabled` should not receive ordinary autonomous chunks but remain visible in status output. The disposition is detected from `.moon/state.json`. Users should be able to reactivate projects manually. If `.moon/brief.md` changes after completion/tabled/needs-direction time, `moon status` should surface that updated guidance exists and that the project is ready for manual reconsideration/reactivation.

### Budget model

The scheduler uses a linear time-aware weekly budget curve with a configurable weekly reserve, defaulting to 25%. It should spend only when weekly remaining quota is above expected remaining quota plus reserve for the current point in the reset cycle. This curve may be adjusted after v1. v1 does not enforce a separate 5-hour reserve before starting, though 5-hour usage should still be reported and monitored during active work. The scheduler also gates automatic work by configured moon work hours. The model must preserve user priority access and avoid aggressive end-to-end consumption.

Budget discovery is a first-class provider interface. The preferred v1 path is OpenAI Codex usage via the `codex-usage` command, with `scripts/codex-usage` retained as a backup/reference copy of the current implementation. The provider should capture remaining 5-hour and weekly quota plus reset times, and convert that into normalized budget state for scheduler decisions. Do not redesign this subsystem for v1; keep parsing isolated behind a small usage/budget interface so it can be replaced later. Pi usage integration via Pi and/or the `npm:@tian.zuo/pi-usage` extension remains a possible fallback. A configured command returning normalized machine-readable budget data is also required as an escape hatch.

### Runner model

The runner invokes Pi through RPC mode inside an ephemeral Docker container to perform work in a chosen project directory. Moon remains the host-side control plane responsible for config, scheduling, budget checks, project selection, Docker orchestration, state updates, and logs. The container is responsible for autonomous project work: inspecting/editing files, running commands/tests, making git commits, updating `.moon/status.md`, and writing `.moon/agent-result.json`.

V1 should maintain best-effort persistent resumable Pi sessions per project, with Pi session storage persisting outside ephemeral Docker containers. Store both Pi session ID and session file/path in `.moon/state.json`. The manual tick MVP remains usable if session resume is imperfect; if a session is lost or unusable, Moon should start another session and rely on repository files, `.moon/status.md`, `.moon/brief.md`, and Git state as durable fallback context. This behavior must be revisited after real-world work because runner behavior and context overhead may force a different approach.

The configured Moon project root should be mounted read/write into the container. User-global Pi skill locations should be mounted read-only. Moon workflow skills should be bundled into the runner image. The host home directory, SSH directory, unrelated repositories, Moon config/runtime directories, Docker socket, and privileged container modes should not be exposed. The runner should aim for non-root execution, sensible host UID/GID ownership, read-only container root filesystem, writable temp dirs as needed, and narrow credential injection rather than mounting the user's full Pi home. The runner should receive project context from `.moon/brief.md`, `.moon/status.md`, and generated instructions requiring status updates.

Each automatic session should calculate an expected maximum duration from the current work-hours schedule, generally ending before the active work window closes. Work chunks should be configurable, defaulting to 20 minutes; exact implementation is delegated to the agent. Chunk control should be cooperative first: near the soft deadline, send a steering instruction to finish the current reasonable atomic operation, update handoff, and prepare to stop. At the hard deadline, use Pi RPC `clear_queue` and `abort`. Process/container termination should be only a watchdog fallback. When a chunk ends, another chunk should start if budget remains available and the current time is still within configured work hours. Wrap-up/status/log updates should not have a strict time limit in v1 and may use a dedicated skill/workflow such as `/moon-chunk-summary` to summarize the chunk. During the session, moon should monitor token usage repeatedly, preferably between resumable work chunks. v1 should start with global `codex-usage`; Pi per-session usage support can be added later and should not block runner implementation. If budget and time remain after a chunk, moon may rotate to another eligible project. If 5-hour tokens expire or weekly remaining quota falls below the current budget threshold, the runner should stop making code changes, update moon/status files with a summary, write logs, and exit cleanly.

### Scheduling

The tool should be runnable by systemd timer. The timer wake interval should be configurable, defaulting to 30 minutes. Each scheduled invocation should check pause state and configured work hours before inspecting or touching projects. Outside work hours, it should exit without touching project directories, optionally updating only global/log state. Inside work hours, it should check budget state before inspecting or touching projects. If budget is insufficient, it should update only global/log state with the reason. If budget is sufficient, it should then discover direct child project directories under the root, initialize all uninitialized projects if needed, choose an eligible project, run work only if safe, and write status. Auto-initialization should happen only inside work hours and after budget passes. Projects whose briefs still contain only the placeholder are not eligible for agent work. `moon tick` should be silent unless errors because humans are not expected to read its normal output.

### Status

`moon status` shows global status, pauses, work-hours state, eligible/completed/tabled projects, and low-priority last-known budget information near the bottom. Global pause state should appear before work-hours information. It should stay concise and should not include recent automatic-run summaries by default. Work-hours state should say whether it is currently work time or no-work time and how long that state will last assuming no config changes. If currently outside work hours, it should show the next work window start time and duration. `moon status <project>` shows project-specific status from `.moon/status.md` and metadata, plus terse versions of the last 3 run summaries.

## Open Questions

- Future project selection algorithm beyond v1 last-run round-robin: priority list, weights, weighted fairness, or hybrid.
- Exact Docker/Pi RPC invocation details, session persistence paths, credential injection, and container hardening settings.
- Exact design for v1 moon-provided skills/workflows for work chunks, chunk summaries, and updating `.moon/brief.md`, especially after grill-me sessions.
- Exact normalized budget command JSON schema.
- Whether `codex-usage` offers stable machine-readable output or must be parsed from human-readable text.
- Whether Pi usage extension exposes stable machine-readable output or whether moonlighter must call extension internals/wrap a script.
- Exact systemd unit/timer installation UX.
- Exact configuration syntax and CLI commands for moon work hours.
- How well best-effort resumable runner sessions work in real-world testing.
- How to define and parse milestones in `.moon/status.md`.
- How projects declare completion in `.moon/status.md`.
