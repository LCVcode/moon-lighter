---
name: moon-work-chunk
description: Moonlighter autonomous work protocol. Use when Moon asks the agent to perform one bounded project work chunk inside a Moon-owned workspace.
---

# Moon Work Chunk

Use this skill only for Moonlighter-managed automatic work chunks.

## Rules

- Treat the current working directory as a Moon-owned project workspace.
- Do not edit `.moon/state.json`; it is Moon-owned machine state.
- Do not push commits or contact remotes unless explicitly instructed by project files.
- Do not start broad rewrites or speculative work that cannot be handed off cleanly.
- Preserve existing user/agent work. Inspect uncommitted changes before editing.
- Do not run budget checks or try to manage token spend; host-side Moon enforces budget before launching chunks. Use `moon-time-left` for chunk timing only.

## Protocol

A Moon work chunk is a bounded work session, not a single-task request. Keep making coherent progress while useful autonomous work remains and time allows.

1. Read `.moon/brief.md`, `.moon/status.md`, and relevant project files such as `README`, `SPEC`, `TODO`, tests, and package metadata.
2. Run `git status --short --branch` and understand any existing uncommitted changes or conflicts.
3. Decide whether there is enough concrete direction to make useful autonomous progress.
4. If direction is insufficient, update `.moon/status.md`, write `.moon/agent-result.json` with `needs_direction`, and stop.
5. Otherwise choose a small, bounded, goal-aligned task.
6. Make useful progress using ordinary engineering judgment.
7. Run obvious relevant checks/tests when practical.
8. Commit coherent completed work at logical task boundaries with clear commit messages.
9. Run `moon-time-left` after each useful task/checkpoint and follow its guidance:
   - `keep working`: identify any high-value autonomous work and keep executing; if no high-value work remains or direction is unclear, mark the project `complete` or `needs_direction` as appropriate and terminate.
   - `wrap up`: quickly finish the current task, commit changes when ready, update handoff files, and terminate.
   - `finish now`: stop immediately, write or verify handoff, and leave changes uncommitted if necessary.
10. Keep `.moon/status.md` updated with concise handoff notes.
11. Before stopping, write `.moon/agent-result.json` with the current disposition and summary.

## Agent Result Schema

Write `.moon/agent-result.json` as JSON:

```json
{
  "disposition": "active",
  "summary": "Concise summary of this chunk and the next useful step."
}
```

Valid dispositions:

- `active`: concrete autonomous work remains.
- `needs_direction`: continuing requires a material user decision or clearer goals.
- `complete`: stated goals or acceptance criteria are affirmatively met.
- `tabled`: the project is deliberately postponed or abandoned.

Do not mark `complete` merely because no TODO is obvious. Prefer `needs_direction` when user input is needed.
