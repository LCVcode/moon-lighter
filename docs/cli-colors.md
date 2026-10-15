# CLI color policy

This pass uses restrained semantic emphasis rather than coloring whole reports.
Labels/headings are cyan, successful actions are green, warnings are yellow,
failures are red, and secondary hints are dim. Paths, prose, numbers, and tree
connectors normally remain plain. Existing status categories retain their useful
accents (for example magenta for requested direction and blue for tabled work).
Color supplements readable words; it never replaces them.

## Control and compatibility

Every parser accepts `--color auto|always|never`, including nested commands:

```bash
moon --color always config check
moon config --color always check
moon config check --color always
moon report --details --color never
```

- Default `auto` enables color only for a terminal. Stdout and stderr are checked
  independently; redirecting stdout does not prevent a terminal error from being red.
- `NO_COLOR` (even empty) or `TERM=dumb` disables automatic color.
- Explicit `always` overrides those environment settings; `never` disables color.
- A later child-command flag overrides an ancestor's flag. Literal arguments after
  `--` are not interpreted as color settings.
- Policy is scoped to one invocation, including help and argument errors.
- Strip the ANSI sequences and the human-readable text, alignment, and exit codes
  are unchanged. No new success messages are added to previously silent commands.
- Generated completion scripts, startup snippets, and systemd units are always plain,
  even with `always`. Version output remains plain. On-disk configs, state, history,
  log files, and startup files do not acquire ANSI codes.
- Editor output and raw systemctl timer tables are not recolored.

## Choices by command

| Command/output | Treatment |
|---|---|
| Root and every command's help | Cyan usage label; bold cyan section headings; option text stays plain |
| Argument/command errors | Red error prefix on stderr; unchanged diagnostic text and exit status |
| `--version` | Plain, stable version string |
| `config init` | Green creation label; cyan paths/metadata labels; dim existing-file notices and next steps |
| `config check` | Cyan metadata labels, green OK, yellow WARNING, red ERROR and failed check |
| `completion bash/zsh/fish` | Always plain generated shell code |
| `setup completion` | Green installed label, dim idempotent notice and restart hint, yellow confirmation prompt |
| `setup completion --print` | Always plain startup snippet |
| `service print` / `service install --print` | Always plain generated units, including comments |
| `service install` / `enable` | Green action confirmation; yellow reminder when timer is not enabled |
| `service disable` | Yellow disabled-state confirmation (not a command failure) |
| `service status` | Cyan heading/labels; green yes, yellow no/unknown; raw timer table stays plain |
| `service uninstall` | Green removals, yellow cleanup warnings on stderr, dim nothing-installed notice |
| `init`, `claim`, `release`, `activate` | Green successful action labels; plain project paths; cyan claim-source label |
| `brief` | Cyan Brief label and plain path; editor output untouched |
| `priority` list/get/set | Urgent bold red, high yellow, normal cyan, low blue, backlog dim; set-action label green; invalid red and uninitialized yellow |
| `pause` / `resume` | Yellow paused state; green resumed action; plain paths |
| `status` / `status <project>` | Preserve category/health colors; complete and successful outcomes green; pause yellow; historical outcomes colored like log statuses; priority tiers shared with `priority`; field labels cyan |
| `log` | Cyan heading and metric labels; success green, failed red, skipped/interrupted yellow, running cyan; unknown/partial/reset warnings yellow; tree structure/prose plain |
| `report [project]` | Cyan title/labels/table header; outcome words follow log palette; unknown/partial/reset warnings yellow; quota caveats, range notes, and detail hints dim |
| `run`, `work` (also legacy `tick`/`light`) | Yellow skip label; silent successful execution remains silent; errors red; inspect successful outcomes with log/report |

Priority red expresses urgency, not failure. A running worker's green health marker
in status is distinct from an unfinished session's cyan `running` outcome.
Budget gate colors remain the existing green allowed/red blocked distinction.

## Validation

Tests cover all human-output command families and help, forced/plain output,
TTY/environment policy, stderr independence, nested flags, invocation isolation,
ANSI-safe report alignment, raw artifact byte equality, and lifecycle confirmations.
No authenticated agent runs or real service-management changes are needed.
