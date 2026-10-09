---
name: moon-lighter-init
description: Use when initializing new Moon-lighter projects via `moon init`. Do not use if the `moon` CLI is unavailable, for existing projects, for `moon claim`, or for ordinary project planning without Moon-lighter initialization.
---

# Moon-lighter Init

Initialize new Moon-lighter projects and write the generated project brief.

This skill is only for new projects created with `moon init`. It does not apply
to existing projects imported into Moon-lighter, such as via `moon claim`.

## Workflow

1. Verify the `moon` CLI is available, such as with `command -v moon`.
2. Ask the user for a description of their project concept. Accept text, a local
   file path, or another user-provided source.
3. Identify the project name from the description. If the name is missing or
   invalid, ask the user for one and offer to propose 1-3 valid names.
4. Run `moon init <project-name>`.
5. Use the generated project path from `moon init` output.
6. Populate `.moon/brief.md` in the generated project.
7. Run the Moon-lighter sanity checks.
8. Show the user the final brief path.

If any command or required file check fails, show the failure to the user and
stop. Do not guess a project path, create missing Moon-lighter structure by
hand, or continue after a failed `moon init`.

## Sanity Checks

After writing `.moon/brief.md`, run:

```sh
moon status
moon status <project-name>
```

Inspect the output to ensure Moon-lighter recognizes the new project and that
nothing looks failed, missing, or inconsistent. If either command fails or the
output looks wrong, show the issue to the user and stop.

## Project Names

Project names must match:

```text
^[a-z]+(-[a-z]+)*$
```

Rules:

- lowercase letters only
- words separated by single hyphens
- no numerals
- no underscores
- no spaces
- no punctuation other than hyphens

Examples:

Acceptable:

- `project-concept`
- `my-new-cool-project`

Unacceptable:

- `My-new-project`
- `project draft`
- `concept-version-12`
- `secret_project`

## Writing `.moon/brief.md`

Write a brief that captures the user's concept with enough specificity for a
coding agent to implement from it without avoidable ambiguity.

Use this structure unless the generated file already provides a required
structure:

```markdown
# <Project Name>

<One or two sentence summary of the project concept.>

## Metadata

- Goal: <Race to MVP | Experiment with concepts | ...>
- Scope: <Local-only simple CLI | Complex multi-component project | Library/package intended for distribution/publication | ...>

## Concept

<Detailed description of the project, including all relevant user-provided
requirements, constraints, users, workflows, interfaces, non-goals, and open
questions.>

## Milestones

1. `<version>` - <milestone name>: <expected outcome>
2. `<version>` - <milestone name>: <expected outcome>
```

For milestone versions, use the `semantic-versioning` skill if available. Keep
milestones ordered and implementation-oriented.
