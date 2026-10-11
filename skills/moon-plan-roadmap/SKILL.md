---
name: moon-plan-roadmap
description: Moonlighter rolling-wave planning protocol. Use when a Moon-owned project lacks a concrete capability roadmap, its next development cycle needs expansion, or a user asks Moon to plan the development path. Do not use for ordinary implementation when a clear next roadmap increment already exists.
---

# Moon Plan Roadmap

Turn project direction into a capability roadmap and a detailed next-cycle integration plan.

## Rules

- Treat `.moon/brief.md` as the desired-state source unless newer user guidance or project files clearly supersede it.
- Inspect the current repository state before planning; do not plan from the brief alone.
- Prefer a durable roadmap in `.moon/roadmap.md` over burying execution plans in `.moon/status.md`. Respect an explicitly requested alternative such as root `ROADMAP.md`.
- Use the `semantic-versioning` skill when choosing version numbers if it is available.
- Keep the roadmap realistic and bounded. Do not invent large speculative features beyond the brief's goal and constraints.
- Do not edit `.moon/state.json` or change package versions merely to record a plan.

## Planning Scopes

Use the hierarchy **capability roadmap → development cycle → implementation increment**.

### Capability roadmap

Map all foreseeable capability cycles from current state to desired state in one pass. Identify cycles by stable names or planning IDs, not reserved release numbers. Record outcomes and dependencies; keep later cycles coarse rather than detailing every task in advance. A cycle is an organizational scope and may span multiple minor and patch releases.

### Next-cycle integration plan

Expand only the next incomplete cycle into an ordered delivery chain:

1. **Foundation:** implement and validate the new capability.
2. **Integration:** identify existing commands, features, workflows, and outputs that should consume it. Plan independently deliverable integrations immediately after the foundation, before unrelated capabilities.
3. **Stabilization:** account for compatibility, missing/error states, documentation, and regression coverage where applicable.

A capability is not fully delivered merely because its data or internal API exists. Account for appropriate consumers and user visibility. Omit inapplicable stages rather than inventing work. Do not defer relevant integrations to a distant generic polish milestone.

Give each increment a concrete scope, dependencies, observable acceptance checks, and completion state. Workers should be able to identify and implement the next increment without re-planning the whole project. A work chunk may complete only part of an increment.

Example delivery chain:

```text
Capability cycle: durable work history
  Foundation: capture summaries, metrics, and usage snapshots
  Integration: existing log output consumes recorded summaries
  Integration: project status consumes recorded outcomes
  Integration: global status consumes recent run history
  Integration: activity reports summarize captured data
  Stabilization: legacy records, interrupted runs, and reset boundaries
Next capability cycle: budget-aware execution control
```

### Version labels

Separate capability/dependency planning from release numbering. Use stable planning IDs for increments; an unresolved release version must not block otherwise concrete implementation.

As an increment's delivered scope becomes concrete, use local versioning policy to classify its public changes and resolve its release version before release, not necessarily before implementation. Under strict SemVer, compatible bug fixes may be patches; new commands or functionality require minor releases even when they integrate an existing capability. Breaking changes require major releases. Do not automatically assign a minor version to a cycle or patch versions to its integrations.

Record resolved release versions and the compatibility rationale back into the roadmap, preserving planning IDs and execution order. Respect existing released versions and explicit version commitments; flag conflicts rather than silently renumbering or changing the project's versioning scheme.

## Protocol

1. Read the brief, status, existing roadmap, README/SPEC/TODO files, tests, and package metadata when present.
2. Identify the current project state, the desired state, and the delta between them.
3. Preserve completed or still-valid plans; revise only entries made stale by project reality or new guidance.
4. Map the capability roadmap and dependencies, then expand the next cycle's foundation, integrations, and stabilization work.
5. Mark the next planned increment clearly enough that `moon-work-chunk` can implement it directly. Flag material decisions requiring user direction rather than guess.
6. Write the roadmap to the agreed path. When the current cycle finishes, reassess project reality and expand the following cycle before starting its implementation.
7. In a Moon-owned workspace, update `.moon/status.md` with a short planning summary and next implementation target. Do not create `.moon/` metadata for a standalone planning request unless requested.
8. If run inside a Moon work chunk, write `.moon/agent-result.json` with disposition `active` unless planning revealed that user direction is required.

## Roadmap Shape

Prefer this structure:

```markdown
# Roadmap

## Current State
<What exists now, including the current version.>

## Desired State
<Target from the brief/user guidance.>

## Capability Roadmap
- <cycle ID> — <capability, outcome, dependencies, status>
- <cycle ID> — <next capability; coarse scope>

## Next Cycle: <capability>

### Next: <increment ID> - <name>
- Release version: unresolved | <resolved SemVer and rationale>
- Stage: foundation | integration | stabilization
- Status: planned | in progress | complete
- Depends on: <increment or prerequisite>
- Goal: <concrete outcome>
- Scope: <specific changes and consumers>
- Acceptance: <observable checks or behavior>

### <increment ID> - <integration name>
- Release version: unresolved | <resolved SemVer and rationale>
- Stage: integration
- Status: planned
- Depends on: <foundation>
- Scope: <existing feature adopting the capability>
- Acceptance: <visible evidence of adoption>

## Decisions and Versioning Notes
<Unresolved material choices or numbering conflicts.>
```

Keep roadmap entries implementation-oriented, not aspirational.
