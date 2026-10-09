# Changelog

All notable changes to Moonlighter will be documented in this file.

This project follows Semantic Versioning.

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
