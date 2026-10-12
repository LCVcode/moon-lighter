# Work history and reports

## Sessions and chunks

One invocation of `moon work` or `moon run` is one session. A work session may
contain multiple project chunks; a blocked session has none. Manual runs have one
logical chunk, displayed without a redundant child row. Tree connectors attach
metrics, summaries, and chunk rows to their session; vertical guides persist through
wrapped summary continuations. Errors and stop reasons also wrap to terminal width,
with continuation text aligned after their labels and tree guides retained.
Elapsed times below a minute use seconds (`3s`), with fractional seconds for
sub-second work (`0.03s`) rather than rounding down to `0m`; longer durations
keep the existing minute/hour/day style.

```text
2026-01-01 02:00  work/systemd success  alpha,beta
  ├─ Tokens: 12,000 partial · Duration: 20m · Quota: 5h −8.0%, week −1.0%
  ├─ 2026-01-01T02:00:00+00:00  alpha  success
  │  └─ Tokens: 12,000 · Duration: 10m · Quota: 5h −5.0%, week −0.6%
  └─ 2026-01-01T02:10:00+00:00  beta  success
     └─ Tokens: no data · Duration: 10m · Quota: 5h −3.0%, week −0.4%
```

`moon log` shows the latest five sessions by default (child chunks do not count
against that limit). Use `moon log --limit N` to show more. Keep using `--project`,
`--status`, and `--all`. Additional
status filters include `running` and `interrupted`. `--color auto|always|never`
controls status and yellow missing/partial-data warnings. Status words use green
for success, red for failure, yellow for skipped/interrupted, and cyan for running;
headers, tree connectors, and summaries are not status-colored. Plain output never relies on color
alone. Project filtering selects sessions containing that project; session totals
still represent the entire selected session, not only that project's child.

Failed sessions collapse to one line in `moon log`: timestamp, trigger, status,
project(s), and failure cause. Long causes are truncated with `…` to terminal width;
full errors, summaries, metrics, and successful sibling chunks remain in
`moon report --details` or `moon report --session RUN_ID`.

Report project tables size all columns from visible text, including partial and
unknown values, excluding ANSI escape codes from padding calculations.

Compact logs omit unobserved quota windows and zero coding fields. Unknown tokens
and durations, partial totals, and reset warnings remain visible. This is display-only:
`moon report --details` retains missing quota and zero coding fields. Missing coding
values are not rendered as `None` or invented as zero.

## Status and activity reports

Status shares merged history with logs/reports, preserves current project disposition,
labels older handoffs as historical, and shows useful work alongside recent failures.
It does not infer a next step from arbitrary prose.

`moon report [project]` supports `--today`, `--week`, `--since`, `--until`,
`--session`, `--details`, `--limit`, `--all`, and `--color`.
Without a range, all retained history is selected. Dates/naive timestamps are local;
offset-aware ISO timestamps identify absolute instants. Starts are inclusive, ends
exclusive, and calendar weeks run Monday through Sunday. Ranges select invocation
starts; all children of selected sessions remain included even across a boundary.
`--until` applies to `--since` or all-history ranges, not `--today`/`--week`.

Reports distinguish parent wall time from summed child time, whole-session outcomes
from matching project chunk outcomes, and complete totals from known partial subtotals.
Project metrics come only from matching chunks; parent wall time is not attributed
to a project. Legacy multi-project chunk attribution remains unknown.
Quota samples are account observations and are never summed as project costs.

Details default to at most 20 sessions (`--limit N`); aggregate totals cover all
selected records. `--session` uses the exact ID shown in `--details`.
Project reports also include matching work context. `--all` includes retained legacy
routine skips, not scheduler skips that were never recorded. Reports and status
are read-only: no work, live quota refresh, or lifecycle reconciliation.
Logs may safely reconcile abandoned starts.

Shared readers preserve readable records and warn when data is corrupt/inaccessible.
Invalid UTF-8 index lines, malformed metadata, and duplicate chunk identities cannot
silently produce complete totals. Valid sidecars override matching index entries;
otherwise the latest appended index entry wins.

## Durable storage

`~/.local/state/moon/reports/<run-id-hash>.json` is an atomic, fsynced structured
report per invocation, containing a session and its chunks. `runs.jsonl` remains
backward-compatible completed-run history. Readers merge them by run ID, prefer
reports, and show unfinished sessions even without a terminal legacy record.
Reports use schema version 1; original run records also retain their own existing
schema version 1. These are distinct storage formats.

Starts are persisted before any corresponding worker launches. A failure to write
history prevents execution; no optional bypass exists in this release. Terminal
write failures surface an error without rolling back successful project work.
Previously persisted starts remain available. Observation failures are separate
from work outcomes.

Per-session file leases protect active reports. Reconciliation marks an ownerless
session interrupted only when any recorded active Docker worker is confirmed gone
or stopped. Unknown Docker state remains unfinished. Reconciliation does not invent
an end time or duration for crashed work. A project usage lease prevents concurrent
Moon chunks from writing the same agent session; an orphaned/unknown container also
blocks a new chunk rather than contaminating usage attribution.

New history records budget blocks and operational failures. Routine outside-window,
paused, and no-eligible-project skips are omitted. `--all` still exposes such entries
in legacy history, but cannot recover entries that were intentionally not stored.

## Timing and usage

Wall-clock start/end timestamps identify when work happened; monotonic durations
measure live execution. Session duration includes gate checks and bookkeeping;
chunk duration measures its runner execution. Unknown crash duration stays unknown.

Session and chunk reports retain available pre/post quota percentages, reset times,
source, timestamps, and errors. Deltas are percentage points of shared account
quota, not exact Moon token consumption. Concurrent external activity may affect
them. The compact display uses `%` for percentage-point differences (not relative
percent changes), shows decreases with a minus sign, and omits the account suffix. A changed/crossed reset is labeled `reset/changed`; missing reset information
is labeled `unknown reset`. Do not sum parent and child quota deltas.

Pi assistant-message usage is collected only from JSONL data appended during the
chunk. Previously resumed-session messages are excluded. Provider `totalTokens`
is authoritative; input/output/cache categories are preserved when available and
not added again to that total. There is no estimate from quota percentage to tokens.
Forked files require trustworthy current-message timestamps; copied old messages
and unattributable messages are excluded. Missing baseline files and unreadable or
truncated data make observations unknown or partial. Append offsets remain
authoritative for reused files even if the wall clock moves backward. Session totals sum known chunk
counts and say `partial` if any chunk lacks a complete count. A session with no
known counts shows `no data` instead of zero.

Reports also retain agent summaries/disposition/stop reason, optional explicit
`current_state` and `next_step`, existing commit/line metrics, provider/model/runner
metadata, and references to detailed project logs. No transcripts or auth secrets
are copied into the report. Missing detailed logs are labeled unavailable without
invalidating captured metrics or summaries.

## Retention and later work

There is no automatic pruning today. Run reports follow the lifetime of run logs;
future explicit retention operations should delete pairs together. Manual removal
of a referenced detailed log does not delete its report. Legacy entries without a
report remain valid and show `no data` for uncaptured usage.

Retention controls and an explicit history-gate bypass flag remain future work;
any bypass must remain independent of budget/schedule bypasses. Capture, log,
status, and report consumers all ship together in 1.2.0.
