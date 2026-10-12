# Work history and reports

## Sessions and chunks

One invocation of `moon work` or `moon run` is one session. A work session may
contain multiple project chunks; a blocked session has none. Manual runs have one
logical chunk, displayed without a redundant child row. Tree connectors attach
metrics, summaries, and chunk rows to their session; vertical guides persist through
wrapped summary continuations.

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
Unreadable/truncated data is unknown or partial. Session totals sum known chunk
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

Deeper `moon report` analysis, report-based status improvements, retention controls,
and an explicit history-gate bypass flag are separate future increments. Any history
bypass must remain independent of budget/schedule bypasses.
