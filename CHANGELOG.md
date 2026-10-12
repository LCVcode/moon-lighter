# Changelog

All notable changes to Moonlighter will be documented in this file.

This project follows Semantic Versioning.

## 1.2.0 - Unreleased

### Added

- Durable per-invocation work reports with parent sessions, child chunks, start and
  outcome records, monotonic duration, summaries, optional handoff context, coding
  metrics, and runner/provider/model metadata.
- Session/chunk quota observations and chunk-local Pi token usage, excluding prior
  resumed-session messages. Unknown and partial token totals remain explicit.
- Safe interrupted-session reconciliation using owner leases and Docker liveness.
- Tree-form `moon log` with a five-session default, readable metrics, status-only
  outcome colors, wrapped summaries/errors/stop reasons, and second-scale durations.
  Manual runs display as one item; work sessions retain nested chunks.
- Shared history queries integrated into project/global status, with meaningful
  summaries, explicit next steps, historical handoff labels, and recent outcomes.
- `moon report [project]` for local calendar/date ranges, aggregate activity,
  matching project contributions, partial/unknown totals, and session/chunk detail.
  Status and reports are read-only and never refresh quota or launch work.

### Changed

- History start persistence is mandatory before launching work. There is no bypass
  flag yet. Post-run usage failures do not invalidate successful project work.
- New history retains budget blocks and operational failures but omits routine
  outside-window, paused, and no-eligible-project skips. Old records remain readable.
- Reports retain metrics when referenced detailed logs disappear; no automatic
  pruning or independent report retention policy is introduced.
- Compact logs omit zero coding fields and unobserved quota windows, while unknown
  tokens/durations and partial totals remain explicit. Report details retain captured
  zero fields and missing-data explanations. `%` denotes account percentage-point
  changes; decreases have a minus sign and the compact account suffix is omitted.

### Fixed

- Align report project-table columns using visible widths, including colored,
  partial/unknown values and wide project names. Failed log sessions now use compact
  single-line causes; full failed-session context remains in report details.
- `moon --version` reads installed package metadata instead of always showing 1.0.0.
- Recognize Docker's lowercase/mixed-case missing-container responses without
  weakening fail-closed handling of unknown/running workers.
- Tolerant history consumers retain readable data around malformed/invalid-UTF-8
  records, report warnings, deduplicate records, and select the latest legacy entry.
- Reject invalid token metadata and duplicate chunk identities; prevent copied,
  timestamp-less fork messages from being charged to a new invocation.
- Handle deleted/unavailable session storage as partial/unknown usage, not failed
  work; normalize quota timestamps/offsets and preserve byte-offset attribution
  across wall-clock changes.

## 1.1.0 - Unreleased

### Changed

- Roadmap planning now maps capability cycles first, then expands the next cycle
  into foundation, integration, and stabilization increments.
- Planning identifiers are independent of release numbers; workers resolve SemVer
  from delivered scope before release and record versions back into the roadmap.
- Autonomous work follows the next planned increment and expands the next cycle
  when needed, without treating unresolved release versions as blockers.

## 1.0.0 - Unreleased

Initial v1 MVP release.

### Added

- Project lifecycle commands for initializing, claiming, releasing, activating, pausing, and resuming projects.
- Per-project Moon metadata under `.moon/`, including brief, status, state, logs, and agent-result handoff files.
- Manual one-chunk execution with `moon run`.
- Scheduled work entry point with `moon work`.
- User-level systemd service/timer management with `moon service`.
- Work-window and budget gates for scheduled work.
- Dockerized Pi runner integration for automatic coding chunks.
- Project priority tiers: `urgent`, `high`, `normal`, `low`, and `backlog`.
- Repo-guided handling for claimed projects with placeholder briefs.
- Run history with `moon log`.
- Global and per-project status views with service, work-window, budget, priority, and feedback visibility.
- Shell completion generation and setup commands for Bash, Zsh, and Fish.
- Bundled Moon workflow skills for work chunks, wrap-up, and brief updates.

### Safety

- Moon checks budget and schedule before scheduled work.
- Systemd invokes plain `moon work`; it does not bypass Moon gates.
- Runner prompts instruct agents not to push and not to manage budget.
- Project state in `.moon/state.json` is Moon-owned.
- `moon release` refuses to overwrite existing destinations.

### Notes

- Token/budget deltas, richer reporting, health checks, alternate runners, project work modes, and improved project summaries are tracked as follow-up issues.
