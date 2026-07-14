# Deploying mealie-mcp (remote HTTP, safe mode, Cloudflare Tunnel)

This server runs as a Docker container in the Mealie box's compose stack,
exposed to the Claude web/mobile app through the existing Cloudflare Tunnel.
Auto-deploy on push to the `deploy` branch is handled by a **self-hosted GitHub
Actions runner installed on the box** (the box is outbound-only, so GitHub's
cloud runners can't reach in).

## Runtime configuration (all via env)

| Var | Deploy value | Notes |
|---|---|---|
| `MEALIE_URL` | `http://mealie:<port>` | Internal service name on Mealie's network (not the public tunnel URL). Confirm the port. |
| `MEALIE_API_TOKEN` | _(secret, in `.env`)_ | Long-lived Mealie token. |
| `MCP_TRANSPORT` | `http` | |
| `MCP_PORT` | `8000` | Tunnel points here. |
| `MEALIE_MCP_MODE` | `safe` | Drops 29 destructive/external tools. |
| `MCP_SECRET_PATH` | _(secret, in `.env`)_ | `openssl rand -hex 24`. Endpoint becomes `/<secret>/mcp`. |
| `MCP_BEARER_TOKEN` | _(optional, in `.env`)_ | Second gate; leave unset to start. |

Secrets live in a gitignored `.env` at the repo root (never committed).

## Facts to fill in (placeholders in the scaffolded files)

Replace these before the first deploy:

- `.github/workflows/deploy.yml`
  - `__HOST_LABEL__` — short slug for the box (also the runner label), e.g. `macmini`.
  - `__SERVER_CLONE_PATH__` — absolute path of this repo's clone on the box.
  - `__COMPOSE_FILE__` — compose file that defines the `mealie-mcp` service.
  - `__COMPOSE_SERVICE__` — the service name (`mealie-mcp`).
- `deploy/docker-compose.mealie-mcp.yml`
  - `__MEALIE_NETWORK__` — Mealie's docker network (`docker network ls`).
  - Internal `MEALIE_URL` port.

## One-time setup on the box

1. Clone the fork on the box (the `deploy` branch) at the chosen path; create
   `.env` there with the secrets above.
2. **Chosen layout: merge** the `mealie-mcp` service (from
   `deploy/docker-compose.mealie-mcp.yml`) into the existing Mealie
   `docker-compose.yml` so it shares Mealie's network, then
   `docker compose up -d mealie-mcp`. Point `__COMPOSE_FILE__` in the workflow
   at that Mealie compose file.
3. Register the self-hosted runner (see the `setup-server-deploy` skill, Step 3):
   dedicated folder `~/actions-runner-mealie-mcp`, `--name macmini-mealie-mcp`,
   `--labels <host-label>`. Install as a service.
4. Add the Cloudflare Tunnel public hostname → `http://mealie-mcp:8000`.
   **Skip Cloudflare Access** on this hostname (it tends to block MCP connector
   traffic); rely on the secret path (+ optional bearer).

## Add to Claude

Custom connector URL: `https://<hostname>/<MCP_SECRET_PATH>/mcp`
(If a bearer token is set, the connector must send `Authorization: Bearer …`.)

## Out-of-band steps the runner does NOT do

- **Cloudflare Tunnel hostname** — added once in the tunnel config, not by CI.
- **Compose structural changes** (networks, new services) — a code push rebuilds
  and restarts the container, but changing the compose file itself still needs a
  manual `docker compose up -d` on the box.
