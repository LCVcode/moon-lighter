---
name: moon-update-brief
description: Update a Moonlighter project's `.moon/brief.md` with clarified user guidance, especially after a grill-me session.
---

# Moon Update Brief

Use this skill when the user wants to update Moonlighter project guidance.

## Protocol

1. Read the existing `.moon/brief.md` if present.
2. Incorporate the user's clarified goals, constraints, non-goals, preferences, and success criteria.
3. Prefer concise structured Markdown over transcripts.
4. Make the brief durable and useful for future autonomous work chunks.
5. Include likely next directions when they are known.
6. Do not directly reactivate projects or edit `.moon/state.json`.
7. Let Moon detect the changed brief and surface reactivation readiness.

A useful brief explains what the project is, what success looks like, important constraints, and likely next steps.
