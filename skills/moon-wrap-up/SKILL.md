---
name: moon-wrap-up
description: Moonlighter chunk wrap-up protocol. Use when Moon asks the agent to stop project work, summarize the chunk, update handoff files, and prepare to exit.
---

# Moon Wrap Up

Use this skill at the end of a Moonlighter work chunk or when Moon asks the agent to stop.

## Protocol

1. Stop starting new implementation work.
2. Run `moon-time-left` if available and obey `wrap up` / `finish now` urgency.
3. Finish only the current safe atomic operation if needed to avoid leaving broken partial edits; if time is effectively gone, leave changes uncommitted rather than starting more work.
4. Inspect `git status --short --branch` and summarize important working-tree state.
5. Run only quick checks that are directly relevant and practical.
6. Update `.moon/status.md` with concise handoff information:
   - what changed
   - current state
   - checks/tests run
   - remaining risks or uncommitted work
   - next concrete step, if any
7. Write a concise project log summary under `.moon/logs/`.
8. Write `.moon/agent-result.json` using the schema below.
9. Leave the workspace in the safest practical state for the next chunk.

Do not push commits. Do not edit `.moon/state.json` directly.

## Agent Result Schema

```json
{
  "disposition": "active",
  "summary": "Concise handoff summary."
}
```

Valid dispositions are `active`, `needs_direction`, `complete`, and `tabled`.
