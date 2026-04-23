# Changelog

## [1.1.2] - 2026-04-23

### Added
- `POST /backup` endpoint — performs atomic, verified SQLite backups with integrity checks
- `POST /reload` endpoint — clears internal client cache to refresh the database index
- Self-healing hints — the daemon now detects "Internal error: Error finding id" during searches and provides actionable advice

### Fixed
- `palace-daemon.service` — port conflict handling: added `ExecStartPre=-/usr/bin/fuser -k 8085/tcp` to ensure port 8085 is free before starting
- Improved service reliability by adding `KillMode=mixed` to `palace-daemon.service`
- `main.py` — added `VERSION` constant and exposed it in `/health`

### Changed
- Updated documentation with API references for new endpoints and clearer systemd instructions

## [1.1.1] - 2026-04-22

### Fixed
- `clients/mempalace-mcp.py` — SyntaxError on startup: `--api-key` argument
  used `default=API_KEY` before `global API_KEY` declaration; changed default
  to `None` so the client actually starts

## [1.1.0] - 2026-04-22

### Added
- `PALACE_MAX_CONCURRENCY` env var (default 4) — tunes read concurrency at runtime
- `clients/mempalace-mcp.py` fallback mode — if the daemon is unreachable at
  startup, falls back to importing `mempalace.mcp_server` in-process instead
  of exiting, so Claude Code keeps working when the daemon is down

### Changed
- Replaced `asyncio.Lock()` with three semaphores for concurrent access control:
  - `_read_sem(N)` — up to N concurrent read-only ops (search, query, stats, …)
  - `_write_sem(N//2)` — up to N//2 concurrent write ops (add, kg mutations, …)
  - `_mine_sem(1)` — one mine job at a time, independent of reads/writes
- `/mine` now uses `_mine_sem` only — long import jobs no longer block read or
  write traffic (requires mempalace ≥3.3.2 for internal mine locking)
- `/health` bypasses all semaphores — always responds immediately even under
  full load, safe for load balancers and monitoring
- `/stats` fans out its three sub-calls with `asyncio.gather()` — response time
  cut to roughly one third of the previous sequential implementation

## [1.0.0] - 2026-04-21

### Added
- `POST /mcp` — full MCP JSON-RPC proxy endpoint
- `GET /health` — daemon + palace status
- `GET /search` — semantic search over palace drawers
- `GET /context` — alias for /search, named for LLM tool prompts
- `POST /memory` — store a drawer (wing, room, content)
- `GET /stats` — wing/room counts, KG stats
- `POST /mine` — run `mempalace mine` under the global asyncio.Lock,
  serializing bulk imports against live queries
- Optional API key auth via `PALACE_API_KEY` env var (`X-Api-Key` header)
- Configurable host, port, palace path via CLI args or env vars
- `clients/mempalace-mcp.py` — zero-dependency stdio MCP proxy for remote clients
- systemd service unit (`palace-daemon.service`)
