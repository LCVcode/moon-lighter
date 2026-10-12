# Moonlighter Roadmap

## Current State

Package version: **1.2.0**, implemented and validated on `feature/durable-history`.
The complete session-history capability is ready for final user acceptance; it has
not been published. Previous master baseline: **1.1.0**, pushed in `bfcb1de`.
Latest existing release tag: `v1.0.0`; neither update has been tagged or published.

The 1.0.0 baseline provides project lifecycle/priority management, manual and
scheduled work, Dockerized Pi/OpenAI Codex execution, host-owned budget/schedule
gates, persisted sessions, status, run history, completion, and systemd management.
CI checks tests, lint, formatting, types, and package builds.

The 1.1.0 update adds rolling-wave capability planning, next-cycle integration
plans, and release numbering resolved from delivered scope. New configs default
to `gpt-6.1-sol`; existing configs are not overwritten.

Completed issues: #2 (systemd management) and #13 (initial CI).
Durable capture, tree-form logs, shared queries, project/global status, and activity
reports are implemented together. User-reviewed real manual-run history informed
log refinements; automated validation uses deterministic runners, not paid agent work.
New chunk controls, work modes, health, onboarding, and alternate backends remain planned.

## Desired State

Make autonomous work understandable, measurable, and controllable. Workers follow
a coherent development path; users can see what changed, observed usage, why work
stopped, and what needs attention. Add explicit work modes and alternate backends
without weakening host-owned gates, workspace preservation, or no-push safety.

## Planning and Release Policy

- Cycle IDs and increment IDs below are planning identifiers, **not versions**.
  The previous proposed `1.1.0` history milestone and `1.1.x` integrations are
  superseded by this plan; they do not describe work delivered in package 1.1.0.
- Map capability cycles broadly; detail only the next incomplete cycle.
- Finish a capability's relevant integrations before unrelated foundations.
  For this project, ship each compatible capability cycle as one minor release,
  including all appropriate consumers, visibility, compatibility, and hardening.
  Internal increments are not separate release targets; subsequent compatible bug
  fixes use patches. Breaking changes still require a major release.
- Resolve each release version from actual delivered public changes using the
  local semantic-versioning skill: new functionality requires a minor bump,
  compatible bug fixes a patch, and breaking changes a major bump.
- The entire session-history cycle targets 1.2.0 relative to committed 1.1.0:
  capture, logs, project/global status, reports, and hardening ship together.
  Do not reserve patch releases to finish intentionally omitted consumers.
- Record resolved versions and rationale alongside completed increments. Preserve
  IDs, dependencies, old configs/history, and existing handoff compatibility.
- Use the project's uv workflow for version metadata changes. Planning alone does
  not change package metadata. Do not tag/publish without an explicit request.
- This root `ROADMAP.md` is the agreed plan; do not create `.moon/` files to mirror it.

## Capability Roadmap

| Cycle ID | Capability / outcome | Dependencies | Status |
|---|---|---|---|
| history | Capture durable work/usage history and integrate it into logs, status, and reports | Existing runner/history | Implemented; final acceptance pending |
| control | Budget-aware chunk guidance and approved pacing options | History observations | Planned; policy decisions needed |
| modes | Strict/MVP/creative behavior integrated with roadmap planning | Existing planning skills; control precedes this cycle | Planned |
| health | Operational diagnostics, actionable output, and relevant status integration | History and gate observations | Planned |
| onboarding | Interactive project creation and complete brief/editor flow | Existing lifecycle commands | Planned |
| backends | Runner abstraction and one additional coding-agent backend | Existing safety/history contracts | Planned; backend decision needed |

## Current Cycle: Durable Work and Usage History

Release target: **1.2.0 — Session history**. All increments in this section share
that release. Each is independently testable and may take multiple chunks. Build
compatibility/failure tests with each increment; final hardening is not permission
to defer correctness.

### history.capture - Durable capture and basic log view

- Stage: foundation
- Status: implemented and committed; final acceptance/publication pending
- Release version: 1.2.0, shared with all history integrations and hardening
- Evidence: deterministic lifecycle, persistence, usage, hierarchy, compatibility,
  and CLI smoke checks; no authenticated agent run was launched for validation
- Clarified scope: `SPEC.md`, `DECISIONS.md`, and `TODO.md` from the grilling session
- Depends on: existing runner results, budget checks, and run history
- Issues: [#7](https://github.com/LCVcode/moon-lighter/issues/7),
  [#11](https://github.com/LCVcode/moon-lighter/issues/11), capture portion of
  [#10](https://github.com/LCVcode/moon-lighter/issues/10).
- Goal: retain enough context to explain individual chunks and whole invocations.
- Scope:
  - Persist timestamped pre/post snapshots with 5-hour/weekly percentages, reset
    times, source, and missing/error states for invocations and individual chunks.
  - Store per-chunk project, summary, disposition, known stop reason, log reference,
    existing commit/line metrics, and runner/provider/model metadata.
  - Preserve explicit current-state/next-step text when supplied; do not invent
    structured information from ambiguous summaries or change required handoff fields.
  - Define backward-compatible storage/readers and delta semantics. Treat usage
    as account-level observations, not precise Moon/project token attribution.
- Acceptance:
  - Successful, failed, interrupted, and multi-project runs retain available data.
  - Old records load; absent snapshots/metrics remain unknown rather than zero.
  - Cross-reset samples are not ordinary consumption; external concurrent usage
    cannot be claimed as exact Moon cost.
  - Preflight usage failures still block work. Post-run observation failures do not
    erase successful work/handoff or prevent its history from being recorded.
- Additional clarified scope:
  - Durable per-invocation reports with session/chunk starts and outcomes. Failed
    start persistence blocks execution; an optional bypass flag is deferred.
  - Prioritize start time, duration, and chunk-local agent token counts alongside
    separate quota observations. Session token totals may be labeled partial.
  - Capture budget blocks and operational failures, not routine scheduler skips.
  - Include a compact hierarchical `moon log` view now: work totals with indented
    children, manual runs flattened, missing metrics labeled `no data`.
  - Reports follow log retention, remain usable if detailed logs disappear, and
    retain interrupted starts pending safe worker-liveness reconciliation.
- First task: define compatible record extensions and old/new-record tests, then
  connect existing runner results and host-side budget observations.

### history.log - Existing log integration (included in history.capture)

- Stage: integration
- Status: implemented, refined, and committed; final acceptance/publication pending
- Release version: 1.2.0, shared with the entire history cycle
- Issues: #11, history consumers from #10
- Scope: retain the existing overview/filters and add compact start time, duration,
  token totals, and 5-hour/weekly deltas. Show work-session totals with indented
  chunks; flatten moon run to one unindented entry. Use recorded summaries/metrics.
- Acceptance: unknown tokens/durations show `no data` (plain when color disabled),
  incomplete totals say partial, and filters still work. Nonessential missing quota
  and zero coding fields are omitted in compact logs but retained in report details.

### history.project-status - Shared history queries and project status

- Stage: integration
- Status: implemented and validated; final acceptance pending
- Release version: 1.2.0 (same session-history release)
- Depends on: history.capture, history.log
- Issue: [#12](https://github.com/LCVcode/moon-lighter/issues/12)
- Implementation steps:
  1. Add shared queries for project chunks, latest meaningful outcomes, most recent
     successful work, and recent failures. Status/report consumers must use the same
     merged history semantics rather than independently parsing JSON or log files.
  2. Make `moon status <project>` use recorded summary, explicit current state/next
     step, disposition context, and the observation timestamp.
  3. Preserve project machine state as the authority for current disposition;
     label older history as historical rather than letting it overwrite newer state.
  4. Use existing handoff/log fallbacks for legacy projects, but reject heading-only
     summaries. Label absent data and timestamp/order mismatches; do not invent a
     staleness age threshold without documenting it.
- Acceptance:
  - Active, complete, and needs-direction projects display useful context.
  - Failed/interrupted work is visible without replacing the last useful successful
    summary with an empty failure record.
  - Old/no-history projects degrade clearly, and status never fabricates a next step.
  - Tests cover mixed legacy/reported history, changed disposition, missing context,
    multiple projects, and missing detailed logs.
- Suggested placement: a focused history-query module plus small status integration
  edits; avoid expanding the CLI entrypoint with aggregation logic.

### history.global-status - Global status integration

- Stage: integration
- Status: implemented and validated; final acceptance pending
- Release version: 1.2.0 (same session-history release)
- Depends on: shared queries from history.project-status
- Implementation steps:
  1. Add a compact history section for last successful work and recent failed or
     interrupted sessions, including timestamp, project(s), and concise cause.
  2. Preserve the existing project, schedule, service, runner, and budget sections.
  3. Clearly distinguish historical usage observations from the current/latest
     budget check and its timestamp. History must never grant permission to work.
- Acceptance:
  - Empty/legacy history, successful sessions, blocked sessions, and operational
    failures produce concise, non-misleading output.
  - Budget/schedule/usage-check reasons remain distinguishable.
  - Status does not run project work or silently change project disposition.

### history.reports - Deep session-history reporting

- Stage: integration
- Status: implemented and validated; final acceptance pending
- Release version: 1.2.0 (same session-history release)
- Depends on: history.capture and shared history queries
- Issues: [#8](https://github.com/LCVcode/moon-lighter/issues/8), report consumers from #10
- Implementation steps:
  1. Finalize a discoverable `moon report` interface for time ranges, project filters,
     and individual-session detail. Proposed time selectors remain `--today`,
     `--week`, and `--since`; finalize date/week/time-zone semantics before coding.
  2. Show aggregate session/chunk counts, success/failure/interruption/block counts,
     durations, projects, manual/systemd breakdown, tokens, and existing coding metrics.
  3. Provide session detail with its child chunks, work summaries, outcomes, explicit
     next steps, and references to available detailed logs. Flatten manual runs in
     the same way as `moon log`.
  4. Aggregate project metrics from matching chunks, not the full parent session.
     Keep session wall time separate from summed chunk execution time.
  5. Calculate known token subtotals with complete/partial/unknown labels. Never
     double-count session and chunk tokens or turn unknown values into zero.
  6. Show qualified account-quota observations separately: resets, missing data,
     and overlapping/external usage prohibit presenting them as exact project cost.
     Do not naively sum parent/child or overlapping quota deltas.
- Acceptance:
  - Empty, legacy, mixed, multi-project, partial, failed, and interrupted histories
    produce tested totals and readable details.
  - Range boundaries, local time handling, project filtering, and skip inclusion
    are documented and tested.
  - Unknown token values and absent log references stay explicit; reports do not
    require exact tokens or later work-mode/pacing functionality.
- Suggested placement: pure aggregation and dedicated report-rendering modules,
  with thin CLI dispatch and deterministic fixture-based tests.

### history.hardening - Complete and validate the 1.2.0 capability

- Stage: stabilization
- Status: implemented and validated; final acceptance pending
- Release version: 1.2.0 (same session-history release)
- Depends on: all history consumers above
- Implementation steps:
  1. Audit capture/read paths before release: start/outcome persistence, concurrent
     readers/writers, report/index deduplication, orphaned workers, malformed/partial
     records, optional observation failures, and resumed-session token attribution.
  2. Exercise capture → log → project/global status → report using shared fixtures.
     Test interrupted/failed/multi-project work, quota resets, unavailable usage,
     old records, missing logs, and color/plain output.
  3. Ensure broken history is surfaced clearly rather than silently yielding
     misleading complete totals or hiding otherwise valid records.
  4. Include the small CLI version fix: read installed package metadata instead of
     hard-coding 1.0.0; regression-test the output (implemented in working tree).
     Update README, detailed history docs, CLI help/completion, and the 1.2.0
     changelog to describe the entire capability. Remove text deferring included
     status/report consumers to later releases.
  5. Run pytest, Ruff lint/format, ty, and package build. Smoke-test the installed
     CLI against isolated reports; reinstall for user acceptance testing.
  6. Record release evidence and resolve outstanding CLI/report policy decisions.
     Commit/review the completed branch when requested; do not tag/publish without
     explicit authorization.
- Release acceptance:
  - Generation, collection, log/status/report consumption, compatibility, and
    failure handling all work together. Capture alone is not release completion.
  - User can inspect both a whole work session and individual chunks without losing
    the distinction between invocation totals and project-specific measurements.
  - No hidden budget bypass, invented usage, or destructive history migration.
  - 1.2.0 remains the package target throughout implementation; internal increments
    do not receive separate release numbers or repeated version bumps.

## Later Cycles: Coarse Scope and Decisions

Expand the next cycle only after reassessing completed history work and user goals.

### control - Budget-aware chunk control and pacing

- Issue: [#3](https://github.com/LCVcode/moon-lighter/issues/3).
- Add host-generated policy and `moon-should-continue` signals: `OK`, `wrap-up`,
  `record-and-end`, `end-urgently`. Preserve `moon-time-left` compatibility.
- Integrate signals into skills/prompts and expose relevant control/pacing context
  in status/reports in the same release; host-owned gates remain authoritative.
- Use captured observations to assess reset-adjacent pacing and quota relationships;
  do not infer absolute quota sizes from a single percentage snapshot.
- User decision: pacing behavior, reserve semantics, initial allowance/tolerance.
  Any new pacing option must be approved and tested at resets, final-day boundaries,
  unknown usage, and 5-hour exhaustion. Retain existing defaults unless a migration
  is explicitly approved. Weekly pacing revision is not yet a GitHub issue.

### modes - Work modes and planning

- Issue: [#6](https://github.com/LCVcode/moon-lighter/issues/6).
- Add `strict`, `mvp`, and `creative`; confirm default/compatibility before shipping.
- Integrate modes into state, CLI/status, planning, execution, and handoff. Include
  mode/next-target visibility, compatibility, and behavioral tests in the same release.
- Workers implement planned increments; bounded creativity never overrides explicit
  constraints. Evaluate existing/missing/stale plans and mode scope boundaries.

### health - Operational diagnostics

- Issue: [#9](https://github.com/LCVcode/moon-lighter/issues/9).
- Add read-only `moon health` diagnostics for config, Docker/image, systemd/Pi PATH,
  usage failures/staleness, invalid states, runner failures, and inactive progress.
- Bundle actionable output, relevant status integration, environment/failure tests,
  and docs in this capability's minor release.
- Distinguish operational errors from informational needs-direction states;
  diagnostics must not launch work or silently mutate services/projects.

### onboarding - Interactive project creation

- Issue: [#4](https://github.com/LCVcode/moon-lighter/issues/4).
- Make missing-name `moon init` interactive only in a terminal; preserve explicit
  automation/editor behavior and show the brief path. Never hang noninteractive use.
- Bundle prompting, brief/editor flow, completion/help, noninteractive behavior,
  error handling, and tests in this capability's minor release.

### backends - Runner abstraction and another backend

- Issue: [#1](https://github.com/LCVcode/moon-lighter/issues/1).
- Separate agent backend from model provider/model with backward-compatible Pi
  defaults. Adapters own invocation/auth/context/sessions/results; Moon owns gates,
  selection, history, state, handoff contracts, and no-push safety.
- Implement one selected backend with explicit isolation/auth/session/usage behavior,
  adapter contract tests, and controlled smoke checks. Fail closed when required
  budget checks cannot be performed; no blanket bypass.
- User decisions: first backend (OpenCode, Codex CLI, or Claude Code), host versus
  Docker execution, and policy for providers without reliable usage APIs.

## Deferred Scope

Optional history-persistence gate bypass flag (separate from budget/schedule
bypasses); exact token attribution without provider support; speculative test metrics;
full CI platform matrix; authenticated agent CI; publishing/deployment automation;
every backend at once; dashboards; new config-editing commands not yet requested.

## Execution and Validation

All history increments are implemented. Final evidence: 227 automated tests, Ruff
lint/format, ty, package build, and isolated installed-CLI capture/log/status/report
smoke checks. Reinstallation is complete; final acceptance remains with the user.
No authenticated agent chunk was launched by the release validation process.
Record progress, acceptance evidence, and resolved versions here. Preserve completed
entries; reassess and detail the following cycle only when it becomes next.

For implemented increments, run focused checks followed by pytest, Ruff lint/format,
ty, and package build as CI does. Update actual behavior and migration notes in docs
and changelog. No implementation or release is implied by editing this plan.
