# Docker/Pi RPC Integration Spike

Date: 2026-09-13

## Summary

Milestone 2 is feasible so far. A local spike runner image was built and used to validate Pi RPC in Docker, session persistence, mounted skills, narrow Codex credential injection, read-only root operation, host UID/GID file ownership, and basic Git availability.

The main implementation constraint discovered is that a fixed non-root user inside the image cannot write arbitrary host-mounted project directories unless host ownership happens to match. The runner should run as the invoking host UID/GID and set `HOME` to a writable mounted runtime home.

## Spike runner image

Temporary image/Dockerfile:

- `docker/moon-runner-spike/Dockerfile`
- local tag: `moonlighter-pi-rpc-spike:local`

Contents:

- `node:22-bookworm-slim`
- Pi `@earendil-works/pi-coding-agent@0.85.1`
- Git, Bash, jq, CA certificates
- non-root `moon` user for image baseline, though actual runs should use host UID/GID

## Validated

### Host skeleton

- `uv run moon --version` works.
- `uv run moon` prints top-level help.
- `ruff`, `ty`, and `pytest` pass.

### Docker and Pi RPC startup

Validated:

- Docker is available.
- Spike image builds successfully.
- `pi --mode rpc` starts in the container.
- `get_state` works in container RPC mode.
- Configured provider/model/thinking flags work for startup:
  - provider: `openai-codex`
  - model: `gpt-5.5`
  - thinking: `minimal`/`medium`
- `--approve` is accepted.

### Writable project root and UID/GID

A first run using the image's fixed `moon` user failed to write to a host temp project mount:

```text
touch: cannot touch 'rpc-created.txt': Permission denied
```

Running the container with the host UID/GID fixed it:

```text
docker run --user "$(id -u):$(id -g)" -e HOME=/home/moon-runtime ...
```

Files created in the project mount were owned correctly on the host (`connor:connor` in the spike).

Conclusion: v1 runner orchestration should run containers as the invoking host UID/GID and mount a writable runtime home.

### Read-only root filesystem

Validated Pi RPC and a tiny prompt while using:

```text
--read-only --tmpfs /tmp:rw,exec,nosuid,size=128m
```

with writable mounts for:

- runtime home
- project root
- session storage

Conclusion: read-only container root appears viable if `/tmp`, runtime home, project root, and session storage are writable.

### Persistent sessions

Validated session creation and reopening across ephemeral containers.

- First container ran a tiny prompt.
- Session JSONL was written under mounted `/sessions`.
- Second container reopened the session with `--session /sessions/<file>.jsonl`.
- `get_state` reported the same session ID/file and message count.

Conclusion: store both session ID and session file/path in `.moon/state.json`; use explicit session file/path where possible.

### Codex auth injection

Attempted `--api-key <host bearer token>` with `openai-codex`; this failed:

```text
No API key found for openai-codex.
```

A narrow mounted runtime home containing only a minimal Pi auth file worked:

```json
{
  "openai-codex": {
    "type": "oauth",
    "access": "<host bearer token>",
    "expires": <future unix ms>
  }
}
```

This allowed containerized Pi to complete a tiny `openai-codex` prompt.

Conclusion: v1 can avoid mounting the host Pi home by creating a Moon-controlled runtime home with a minimal `~/.pi/agent/auth.json` containing a fresh host-exported bearer token. Refresh remains host-side via `pi auth print-bearer-token --provider openai-codex --min-expiry ...`.

### Skills and mount permissions

Validated via `get_commands`:

- User-global skills mounted read-only at `/home/moon-runtime/.pi/agent/skills` are discovered as user skills.
- Explicit Moon skill path passed with `--skill /opt/moon/skills/moon-work-chunk` is discovered.
- Project-local `.pi/skills` under `/workspace` is discovered when using `--approve`.

Also validated that an attempted write into the mounted user skills directory fails with `Read-only file system`.

Conclusion:

- User-global skills can be mounted read-only.
- Moon workflow skills should be bundled into the runner image and explicitly loaded/invoked.
- Project-local skills work under the workspace with `--approve`.
- Moon should pre-create runtime-home subdirectories and mount targets with host ownership; Docker may otherwise create missing nested bind-mount targets as root-owned directories on the host.

### Git availability and host metrics

Validated inside the container:

```text
git version 2.39.5
```

Also validated:

- container-created files in the project mount have correct host ownership when using host UID/GID
- container Git can commit inside the mounted repository
- host-side Moon can measure `HEAD` before/after and compute `git diff --stat <before>..<after>` after container exit

## Not yet validated

- Cooperative steering for active agent work.
- Full RPC abort response timing. A repeatable script, `scripts/spike-pi-rpc-control.py`, validates idle `clear_queue`, direct RPC `bash` cancellation with `abort_bash`, and LLM tool-use cancellation with `clear_queue` then `abort`. A prompt that starts `sleep 60` via the bash tool is interrupted successfully: the bash tool ends with `Command aborted` and the agent emits `agent_settled`. In Pi 0.85.1, the spike still does not observe an explicit `abort` response before settlement, so implementation should treat `agent_settled` after abort as sufficient and not rely solely on an abort response.
- Watchdog fallback details beyond the RPC-level behavior above.
- Full disposable project edit + git commit by the LLM.
- Broader unrelated host filesystem isolation beyond confirming no host home mount and using narrow mounts.
- Read-only user skill mount write-protection with an attempted write.
- Custom additional user-configured Pi skill paths beyond standard global locations.
- Long-lived token refresh behavior across repeated chunks.

## Implementation guidance from spike

- Generate Docker commands internally; do not expose raw Docker UX.
- Use host UID/GID and writable mounted `HOME`.
- Keep container root read-only with tmpfs `/tmp` if practical.
- Mount project root RW.
- Mount persistent session storage RW.
- Mount user-global skills RO.
- Bundle Moon workflow skills into the image and pass/load them explicitly.
- Build a minimal runtime home rather than mounting `~/.pi/agent` wholesale.
- Use explicit `--session <path>` for resume instead of `--continue`.
- For direct RPC bash cancellation, `abort_bash` returns success and the bash response reports `cancelled: true`.
- For agent chunk cancellation, send `clear_queue` before `abort`, then wait for `agent_settled`; do not rely solely on seeing an immediate abort command response.
- If `agent_settled` does not arrive within a bounded timeout, escalate to process/container termination as a watchdog fallback.
