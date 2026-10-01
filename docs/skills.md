# Moonlighter Skills

Moonlighter ships Pi skills for autonomous project work. During development they live in the repo-level `skills/` directory. The runner image bundles them at `/opt/moon/skills/`.

## Skills

- `moon-work-chunk`: bounded autonomous project work inside a Moon-owned workspace.
- `moon-wrap-up`: chunk deadline wrap-up, status/log handoff, and agent-result writing.
- `moon-update-brief`: human-guided updates to `.moon/brief.md`, especially after clarification sessions.

## Human usage

From this repository checkout:

```bash
pi --skill ./skills/moon-update-brief
```

For explicit automatic-work protocol testing:

```bash
pi --skill ./skills/moon-work-chunk --skill ./skills/moon-wrap-up
```

Inside the Docker runner image, Moon loads workflow skills from bundled paths:

```bash
pi --mode rpc \
  --approve \
  --skill /opt/moon/skills/moon-work-chunk \
  --skill /opt/moon/skills/moon-wrap-up
```

Moon also prompts the RPC session with `/skill:moon-work-chunk` at chunk start and `/skill:moon-wrap-up` near the deadline so skill use is explicit rather than relying only on automatic selection.

## Handoff contract

Agents must not edit `.moon/state.json`. They communicate requested project state through `.moon/agent-result.json`:

```json
{
  "disposition": "active",
  "summary": "Concise handoff summary."
}
```

Valid dispositions are `active`, `needs_direction`, `complete`, and `tabled`.
