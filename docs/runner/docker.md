# Docker Runner Notes

Moonlighter V1 runs Pi inside ephemeral Docker containers controlled by the host-side `moon` process.

## Image

Development image tag:

```text
moonlighter-runner:0.1.0-dev
```

Build locally:

```sh
docker build -f docker/runner/Dockerfile -t moonlighter-runner:0.1.0-dev .
```

The Dockerfile currently pins Pi with `ARG PI_VERSION=0.85.1`.

## Required mounts

- project root → `/workspace` read/write
- persistent Pi sessions → `/sessions` read/write
- generated runtime home → `/home/moon-runtime` read/write
- user-global Pi skills → standard Pi skill paths, read-only, when present

Moon workflow skills are bundled in the image at `/opt/moon/skills`.

## Runtime expectations

Run as host UID/GID so edited files remain host-owned. Use a read-only root filesystem with tmpfs `/tmp` when practical. Inject a minimal Pi auth file into the generated runtime home rather than mounting the user's full Pi home.

## Skill paths

Moon should explicitly load/invoke workflow skills from:

```text
/opt/moon/skills/moon-work-chunk
/opt/moon/skills/moon-wrap-up
/opt/moon/skills/moon-update-brief
```
