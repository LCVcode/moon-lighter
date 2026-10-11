---
name: moon-plan-roadmap
description: Moonlighter planning protocol. Use when a Moon-owned project has a desired direction but lacks a concrete versioned roadmap, or when a user asks Moon to plan the development path. Do not use for ordinary implementation when a clear next roadmap item already exists.
---

# Moon Plan Roadmap

Use this skill to turn project direction into a concrete versioned development path.

## Rules

- Treat `.moon/brief.md` as the desired-state source unless newer user guidance or project files clearly supersede it.
- Inspect the current repository state before planning; do not plan from the brief alone.
- Prefer a durable roadmap in `.moon/roadmap.md` over burying execution plans in `.moon/status.md`.
- Use the `semantic-versioning` skill when choosing version numbers if it is available.
- Plan enough detail for future autonomous workers to identify and implement the next update without re-planning.
- Keep the roadmap realistic and bounded. Do not invent large speculative features beyond the brief's goal and constraints.
- Do not edit `.moon/state.json`.

## Protocol

1. Read `.moon/brief.md`, `.moon/status.md`, existing `.moon/roadmap.md` if present, README/SPEC/TODO files, tests, and package metadata.
2. Identify the current project state, the desired state, and the delta between them.
3. If an existing roadmap is present, preserve completed or still-valid planned versions and revise only the parts made stale by project reality or new guidance.
4. Define a versioned path from current state to desired state:
   - each planned version has a concrete outcome
   - each version lists the feature set or stabilization work to implement
   - early versions should produce usable, testable increments
   - later versions may be coarser when uncertainty is unavoidable
5. Mark the next planned version clearly enough that `moon-work-chunk` can implement it directly.
6. Update `.moon/roadmap.md`.
7. Update `.moon/status.md` with a short planning summary and the next implementation target.
8. If this was run inside a Moon work chunk, write `.moon/agent-result.json` with disposition `active` unless planning revealed that user direction is required.

## `.moon/roadmap.md` Shape

Prefer this structure:

```markdown
# Roadmap

## Current State

<Concise summary of what exists now.>

## Desired State

<Concise summary of the target from the brief/user guidance.>

## Version Plan

### Next: <version> - <name>

- Goal: <concrete outcome>
- Scope:
  - <feature/stabilization item>
  - <feature/stabilization item>
- Acceptance:
  - <observable check or behavior>

### <version> - <name>

- Goal: <concrete outcome>
- Scope:
  - <item>
- Acceptance:
  - <check>
```

Keep roadmap entries implementation-oriented, not aspirational.
