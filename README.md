# palace-daemon (jphein fork)

**JP's production fork of [rboarescu/palace-daemon](https://github.com/rboarescu/palace-daemon)**

[![version-shield](https://img.shields.io/badge/version-1.7.0-4dc9f6?style=flat-square&labelColor=0a0e14)](https://github.com/jphein/palace-daemon/releases) [![upstream-shield](https://img.shields.io/badge/upstream-1.5.1-7dd8f8?style=flat-square&labelColor=0a0e14)](https://github.com/rboarescu/palace-daemon/releases)
[![python-shield](https://img.shields.io/badge/python-3.12+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8)](https://www.python.org/)
[![license-shield](https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14)](LICENSE)

---

Fork of [rboarescu/palace-daemon](https://github.com/rboarescu/palace-daemon), tracking `upstream/main` through the 2026-04-25 sync (upstream shipped [v1.5.1](https://github.com/rboarescu/palace-daemon/commit/d0aabb9) on 2026-04-25; this fork is at v1.7.0 with the additional `/graph` endpoint, `/viz` status dashboard, auto-repair-on-startup, and the post-merge deployment tooling). Running in production since 2026-04-24, currently fronting the [jphein/mempalace](https://github.com/jphein/mempalace) **150,814-drawer** canonical palace on [`disks.jphe.in:8085`](https://palace.jphe.in/health). The bulk of the v1.5.0 daemon work (cold-start warmup, `/repair`, `/silent-save`, themed messages, `--palace` flag, MCP timeout) was contributed back to upstream and merged via [PR #4](https://github.com/rboarescu/palace-daemon/pull/4) on 2026-04-25.

What this fork adds that you won't get from upstream yet: a **`GET /viz` status dashboard** (self-contained HTML page that fetches `/graph`, `/repair/status`, and `/health` in parallel and renders five panels — status strip with repair pulse, D3 force-directed knowledge graph, Mermaid wing/room hierarchy, tunnels list, wings bar chart — D3 + Mermaid via CDN, no static-file deps); a **`GET /graph` endpoint** (single-shot structural snapshot for SME-style consumers, ~0.4s on the 151K-drawer palace via direct read-only sqlite reads of `embedding_metadata` and `knowledge_graph.sqlite3` — vs. ~60-120s for the equivalent serial MCP composition under load); **auto-repair-on-startup** that detects degraded HNSW recall after restart and fires `/repair {mode:rebuild}` non-blocking in the background (workaround that bought time for the mempalace fork's `645ba20` integrity gate fix to land); **`kind=` query-param filter** on `/search` and `/context` that excludes Stop-hook auto-save checkpoints by default (mirrors the fork mempalace's checkpoint-filter — keeps high-density session summaries from dominating retrieval); the **`limit=` parameter actually being honored** (earlier versions silently capped at 5 due to a max_results→limit name mismatch the MCP tool's whitelist dropped); a **`scripts/deploy.sh`** that bundles `git push → wait for sync → systemctl restart → /health poll → verify-routes smoke test` into one command; **`scripts/verify-routes.sh`** as a curl-based smoke test for every public route; **`clients/palace-mode`** CLI for one-command local↔remote palace switching; **`clients/palace-mcp-dispatch.sh`** that picks daemon vs. in-process MCP based on `PALACE_DAEMON_URL`; and **`clients/mempal-fast.py`** — a stdlib-only Stop/PreCompact hook handler that POSTs to `/silent-save` without importing mempalace (so cold hook fires can't trigger ChromaDB's HNSW SIGSEGV class). Full list below.

[v1.7.0 release notes](CHANGELOG.md) · [PR #4 — upstream contribution](https://github.com/rboarescu/palace-daemon/pull/4) · [Discussion #5 — Postgres backend](https://github.com/rboarescu/palace-daemon/discussions/5) · [Discussion #6 — TS rewrite heads-up](https://github.com/rboarescu/palace-daemon/discussions/6) · [`docs/event-log-frame.md`](docs/event-log-frame.md) — daemon-as-view-coordinator architectural frame

## Fork change queue

Everything the fork has ahead of upstream, ranked from easiest follow-up PR to hardest. Contributors: rows near the top are smallest and lowest-risk.

Status legend: a PR number means there's an open upstream PR for the change; **PR pending** means the fork has the change but no PR has been filed yet; **PR candidate** means the fork has the change, no PR yet, and it's scheduled to be proposed upstream after the maintainer has had time to use the merged v1.5.0 day-to-day. Per [PR #4 issue comment](https://github.com/rboarescu/palace-daemon/pull/4#issuecomment-4321234194), the offer to send post-1.5.0 work as small separate PRs is open at whatever cadence the maintainer wants.

| Area | Change | Status | Size | Risk | Files |
|---|---|---|---|---|---|
| **Tooling** | `scripts/deploy.sh` — one-command `git push → wait for sync → systemctl restart → /health poll → verify-routes` deploy. Reads `PALACE_API_KEY` from `~/.claude/settings.local.json` env block, fails fast on sync lag. | PR pending — fork commit [`92cbd35`](https://github.com/jphein/palace-daemon/commit/92cbd35) | small | none | `scripts/deploy.sh` |
| **Ops** | `scripts/auto-repair-if-empty.sh` — `ExecStartPost` script that probes `/search` after the daemon binds, detects the "vector ranked 0" warning that emits when HNSW is empty/quarantined despite a populated SQLite, and fires `/repair {mode:rebuild}` non-blocking in the background. Self-heal workaround for the false-positive HNSW-quarantine cascade observed on cold starts; idempotent, no-op when the index is healthy. Coordinated cross-repo with the mempalace-fork integrity-gate fix (`jphein/mempalace` `645ba20`) — once that deploys, the script transitions from hot-path workaround to safety net. **Follow-up `252ebf1`: bumped the daemon-up wait from 30s → 240s (env-overrideable via `PALACE_AUTO_REPAIR_WAIT_SECS`). On a 151K-drawer palace, HNSW segment load takes ~4:48; the prior 30s timeout caused the script to bail exactly when auto-repair was most needed.** | PR pending — fork commits [`ed3a892`](https://github.com/jphein/palace-daemon/commit/ed3a892), [`252ebf1`](https://github.com/jphein/palace-daemon/commit/252ebf1) | small | low | `scripts/auto-repair-if-empty.sh`, `palace-daemon.service` |
| **Tooling** | `scripts/verify-routes.sh` — curl-based smoke test that exercises every public route post-restart. Designed for manual deploy validation, not CI (depends on a live palace). | PR pending — fork commits [`b4b39fc`](https://github.com/jphein/palace-daemon/commit/b4b39fc), [`f832f66`](https://github.com/jphein/palace-daemon/commit/f832f66) | small | none | `scripts/verify-routes.sh` |
| **API** | `kind=` query-param on `/search` and `/context` — three values: `content` (default, excludes Stop-hook checkpoints), `checkpoint` (recovery/audit), `all` (no filter). Companion to the mempalace-fork checkpoint filter; backed by `mempalace.searcher`'s read-side `kind=` parameter. Invalid values return 400. | PR pending — fork commit [`b4b39fc`](https://github.com/jphein/palace-daemon/commit/b4b39fc); requires fork mempalace until upstream lands the searcher-side filter | small | low | `main.py` |
| **API** | `limit=` actually honored on `/search`/`/context`. Earlier code passed `max_results` to the `mempalace_search` MCP tool, but the tool's input_schema declares `limit` — `handle_request` silently dropped the unknown key, capping every response at the default 5 regardless of what the caller asked for. | PR pending — fork commit [`b4b39fc`](https://github.com/jphein/palace-daemon/commit/b4b39fc) | tiny | none | `main.py` |
| **API** | `_canonical_topic()` rewrites legacy synonyms (currently `"auto-save"` → `"checkpoint"`) at the daemon boundary with a warning log line. Defense-in-depth so client-side topic drift can't silently leak into palace metadata. | PR pending — fork commit [`dd8894c`](https://github.com/jphein/palace-daemon/commit/dd8894c) | tiny | none | `main.py` |
| **API** | `GET /graph` — single-shot structural snapshot for SME-style consumers. Mirrors `/stats`'s asyncio.gather shape but reads wings + rooms directly from `chroma.sqlite3.embedding_metadata` and KG entities + triples from `knowledge_graph.sqlite3`, leaving only `graph_stats` and `kg_stats` going through MCP. ~200× faster than the serial MCP composition (~0.4s vs. 60-120s under contention), semaphore-free for the heavy parts. | PR pending — fork commits [`2003e80`](https://github.com/jphein/palace-daemon/commit/2003e80), [`127bf68`](https://github.com/jphein/palace-daemon/commit/127bf68), [`7ee7d0c`](https://github.com/jphein/palace-daemon/commit/7ee7d0c); spec at [`docs/graph-endpoint.md`](docs/graph-endpoint.md); coordinated with the [`multipass-structural-memory-eval`](https://github.com/M0nkeyFl0wer/multipass-structural-memory-eval) palace-daemon adapter | medium | low | `main.py`, `scripts/verify-routes.sh`, `docs/graph-endpoint.md`, `CHANGELOG.md` |
| **API** | `GET /viz` — self-contained status dashboard. Single HTML page (D3 + Mermaid via CDN, no static-file deps) that fetches `/graph`, `/repair/status`, and `/health` in parallel and renders five panels: status strip (version/drawers/repair pulse/pending), D3 force-directed knowledge graph, Mermaid wing/room hierarchy, tunnels list with click-to-highlight, wings bar chart. Optional `?refresh=N` for auto-refresh, `?key=…` for ergonomic auth bookmarking. All wing/room/entity names enter the DOM via `textContent`/`setAttribute`, never `innerHTML`. Inspired by upstream PRs #1022 (D3 KG viz), #393 (Mermaid diagrams), #431 (CLI stats), #256 (sync_status MCP), #601 (brief overview) — none cherry-picked; the page consumes our own `/graph`. | PR pending — fork commit [`00ec6be`](https://github.com/jphein/palace-daemon/commit/00ec6be) | medium | low | `main.py`, `static/viz.html`, `scripts/verify-routes.sh`, `CHANGELOG.md` |
| **API** | `/graph.tunnels` derives from `mempalace_graph_stats.top_tunnels` instead of the broken `mempalace_list_tunnels` (mempalace 3.3.4 — `list_tunnels` returns `[]` while `graph_stats.tunnel_rooms` reports 9 on the canonical palace). Until that's reconciled upstream, the fork prefers `graph_stats` so `/graph.tunnels` and `/stats.graph.tunnel_rooms` always agree. | PR pending — fork commit [`127bf68`](https://github.com/jphein/palace-daemon/commit/127bf68); upstream fix tracked in [`docs/graph-endpoint.md`](docs/graph-endpoint.md) Part 2 | small | low | `main.py` |
| **Clients** | `clients/palace-mode` — shell CLI that flips between local (in-process) and remote (daemon) palace modes by toggling `PALACE_DAEMON_URL` in `~/.claude/settings.local.json`. Subcommands: `status`, `local`, `remote [URL]`, `install` (idempotent re-apply of plugin-cache customizations after a plugin update), `verify`. | PR pending — fork commits [`f8e0faa`](https://github.com/jphein/palace-daemon/commit/f8e0faa), [`f1910d3`](https://github.com/jphein/palace-daemon/commit/f1910d3), [`d450cef`](https://github.com/jphein/palace-daemon/commit/d450cef) (post-review key/path cleanup) | medium | low | `clients/palace-mode` |
| **Clients** | `clients/palace-mcp-dispatch.sh` — thin wrapper invoked by the plugin's MCP server command. Dispatches to `mempalace-mcp.py --daemon $URL` when `PALACE_DAEMON_URL` is set; falls back to in-process `python -m mempalace.mcp_server` otherwise. Resolves siblings via `readlink -f`/`dirname`, no hardcoded absolute paths. | PR pending — fork commit [`f8e0faa`](https://github.com/jphein/palace-daemon/commit/f8e0faa), portable-path fix in [`d450cef`](https://github.com/jphein/palace-daemon/commit/d450cef) | tiny | none | `clients/palace-mcp-dispatch.sh` |
| **Clients** | `clients/mempal-fast.py` — stdlib-only Stop/PreCompact hook handler. Counts human messages in the transcript, gates on `SAVE_INTERVAL`, POSTs to `$PALACE_DAEMON_URL/silent-save`. No `mempalace` import, no chromadb load — so cold hook fires can't trigger the chromadb HNSW SIGSEGV class that the warmup patch addresses for the daemon itself. | PR pending — fork commit [`f8e0faa`](https://github.com/jphein/palace-daemon/commit/f8e0faa) | medium | low | `clients/mempal-fast.py` |
| **Docs** | `docs/event-log-frame.md` — articulates the architectural frame that mempalace is event-streaming-shaped (Kleppmann's "Turning the database inside-out") and palace-daemon is the materialized-view coordinator over the log. Maps mempalace components to log-vs-view roles, identifies which daemon implementation details are chroma-specific vs. role-level. Reference doc, no code changes. | PR pending — fork commit [`432b3a6`](https://github.com/jphein/palace-daemon/commit/432b3a6); intended to be linkable from upstream Discussion #5 once the maintainer has had more time with the merged daemon | medium | none | `docs/event-log-frame.md` |
| **Docs** | `docs/graph-endpoint.md` — plan/reference for the `GET /graph` endpoint and the `mempalace_list_tunnels` inconsistency. Marked SHIPPED at the top with the 1.6.0 commit hashes and live perf numbers. | PR pending — fork commit [`450cca3`](https://github.com/jphein/palace-daemon/commit/450cca3) | medium | none | `docs/graph-endpoint.md` |

## What this looks like in practice

The fork's `/graph` endpoint replaces what an SME-style adapter would otherwise compose by serially calling `list_wings` + `list_rooms × N` + `list_tunnels` + `kg_stats` over MCP:

```bash
$ time curl -sS -H "X-Api-Key: $KEY" https://palace.jphe.in/graph | jq '{
    wings: (.wings | length),
    pairs: ([.rooms[] | .rooms | length] | add),
    tunnels: (.tunnels | length),
    kg: {entities: (.kg_entities | length), triples: (.kg_triples | length)}
  }'
{
  "wings": 36,
  "pairs": 165,
  "tunnels": 9,
  "kg": { "entities": 6, "triples": 3 }
}

real    0m0.876s
```

Deploy is a single command that catches sync-lag footguns (Syncthing-mirrored deployment between dev and prod hosts):

```bash
$ scripts/deploy.sh
▸ 1/5  push to origin           ✓ pushed 00ec6be → origin/main
▸ 2/5  wait for sync to disks   ✓ remote at 00ec6be
▸ 3/5  restart palace-daemon    ✓ restart issued
▸ 4/5  wait for daemon health   ✓ healthy on v1.7.0 (after 3s)
▸ 5/5  smoke-test routes        ✓ all 12 routes verified

✦ deploy complete: 00ec6be on http://disks.jphe.in:8085
```

Local↔remote palace switching is one command:

```bash
$ palace-mode status
Mode: remote (http://disks.jphe.in:8085)

$ palace-mode local
→ local mode

$ palace-mode remote http://staging:8085
→ remote mode (PALACE_DAEMON_URL=http://staging:8085)
```

A Stop hook fires from any Claude Code session and routes through the daemon without ever loading mempalace locally:

```
[06:29:17] Daemon silent-save: queued=False count=14 (fast-path)
[06:29:17] Skipping auto-ingest: PALACE_DAEMON_URL set, daemon owns writes
```

The `/viz` dashboard is a single bookmark for live state — drawer count, repair pulse, KG, wing/room tree, tunnels:

```
https://palace.jphe.in/viz?key=$KEY&refresh=15
```

Auto-repair self-heals after a daemon restart that leaves HNSW empty (the false-positive quarantine cascade — pre-fix shape):

```
06:56:42  systemd: Starting palace-daemon...
06:56:45  Quarantined 3 stale HNSW segment(s) — ChromaDB will rebuild indexes
06:57:19  [auto-repair] daemon up after 15s
06:57:20  [auto-repair] DETECTED degraded HNSW recall: vector ranked 0
06:57:20  [auto-repair] kicking off /repair {mode:"rebuild"} in background — daemon stays available
```

After the mempalace-fork integrity-gate fix (`645ba20`) deployed alongside, the same restart now logs the post-fix shape and the auto-repair script exits no-op:

```
HNSW mtime gap 11165s on .../f360e835-... exceeds threshold but segment metadata file is intact — flush-lag, not corruption. Leaving in place.
HNSW mtime gap 11165s on .../02660268-... — Leaving in place.
HNSW mtime gap 11166s on .../4697d280-... — Leaving in place.
[auto-repair] HNSW recall looks healthy (no 'vector ranked 0' warning)
```

## Why this fork exists

The upstream daemon focused on **stability** — semaphore-coordinated reads/writes, mine isolation, MCP-safe API key auth. JP's fork extended that into **production deployment patterns**:

1. **Single-source-of-truth daemon for distributed Claude Code sessions.** Multiple Claude Code instances (different projects, different terminals, different machines) all routing through one daemon prevents the kind of concurrent-writer SQLite corruption that took down the canonical palace on 2026-04-24. The fork's daemon-strict mode (in [jphein/mempalace](https://github.com/jphein/mempalace)) plus this daemon's queue-and-drain plus `mempal-fast.py`'s no-import path together make that single-writer guarantee enforceable.

2. **Structural snapshots for evaluation frameworks.** When SME ([multipass-structural-memory-eval](https://github.com/M0nkeyFl0wer/multipass-structural-memory-eval)) needed a structural view of the palace for diagnostics, composing it serially over MCP timed out at 60-120s. The fork added `GET /graph` so an evaluator can pull wings, rooms, tunnels, KG entities, and KG triples in one HTTP roundtrip — sub-second on a 151K-drawer palace.

3. **Operational ergonomics.** `palace-mode` for switching local/remote, `deploy.sh` for the one-command release, `verify-routes.sh` for post-restart smoke testing — these are quality-of-life pieces for a daemon that's actually used day-to-day rather than just installed.

The architectural argument for why those pieces survive backend swaps (chroma → pgvector, etc.) is in [`docs/event-log-frame.md`](docs/event-log-frame.md).

## Architectural principles

1. **Single-writer enforced by design.** SQLite + Syncthing replication + multiple writers = corruption. The daemon is the only process that writes to the palace; clients route through it via HTTP/MCP. The fork's `mempal-fast.py` and `palace-mcp-dispatch.sh` make that property hold even for hooks and MCP servers.

2. **Direct sqlite reads for structural data.** `embedding_metadata` and `knowledge_graph.sqlite3` are read-only via `?mode=ro` URI for `/graph`. Bypasses the MCP read semaphore entirely, ~200× faster than the equivalent fan-out under load. Same pattern, different table, for the KG.

3. **Themed messages for save/repair lifecycle.** `messages.py` returns user-facing strings in `systemMessage` so a Claude Code Stop hook surfaces `✦ N memories woven into the palace` without the client knowing the internal save/queue state.

4. **Coordinated rebuild with queue-and-drain.** `/repair mode=rebuild` holds every read/write/mine semaphore slot during the destructive collection swap; `/silent-save` queues to `<palace>/palace-daemon-pending.jsonl` and replays automatically post-rebuild. No saves lost during a rebuild window.

5. **Deploy and verify are the same command.** `deploy.sh` exits non-zero on sync lag, restart failure, or any verify-routes regression. The default cadence for shipping a daemon change is push + restart + verify; if any step fails the deploy aborts, leaving the previous version running.

## Setup

### Requirements
- Python 3.12+
- mempalace (the [fork](https://github.com/jphein/mempalace) recommended for the `kind=` searcher filter and daemon-strict hook mode)

### Install

```bash
git clone https://github.com/jphein/palace-daemon.git
cd palace-daemon
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run (manual)

```bash
# Default: port 8085, palace at $PALACE_PATH or ~/.mempalace/palace
python main.py

# Custom palace path + auth
PALACE_API_KEY=$(openssl rand -hex 32) python main.py --palace /mnt/raid/projects/mempalace-data/palace
```

### Run (systemd user service)

```bash
mkdir -p ~/.config/systemd/user/
cp palace-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now palace-daemon
```

Edit the service file to set `PALACE_API_KEY`, `MEMPALACE_PALACE`, and any custom args before installing.

> [!WARNING]
> **Never install both system AND user services.** They'll fight for port 8085 and the second instance will crash-loop. Pick one.

> [!CAUTION]
> **Don't expose port 8085 without setting `PALACE_API_KEY`.** The `/mine` endpoint accepts arbitrary filesystem paths.

### Plugin client setup

Use `palace-mode install` to wire the [mempalace plugin](https://github.com/MemPalace/mempalace) cache to talk to this daemon (after pointing `PALACE_DAEMON_URL` at it):

```bash
export PALACE_DAEMON_URL=http://your-host:8085
export PALACE_API_KEY=...
~/Projects/palace-daemon/clients/palace-mode install
~/Projects/palace-daemon/clients/palace-mode verify
```

This installs `mempal-fast.py` as the Stop/PreCompact hook handler and `palace-mcp-dispatch.sh` as the MCP server command in the plugin cache. Idempotent — safe to re-run after plugin updates.

## API

| Route | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness + version |
| `/search` | GET | Semantic search; `kind=content\|checkpoint\|all`, `limit=N` |
| `/context` | GET | Same as `/search`, formatted for LLM prompts |
| `/stats` | GET | Aggregate KG + graph + status counts |
| `/graph` | GET | Single-shot structural snapshot (wings, rooms, tunnels, KG) — see [`docs/graph-endpoint.md`](docs/graph-endpoint.md) |
| `/viz` | GET | Self-contained HTML status dashboard (D3 + Mermaid). Optional `?refresh=N`, `?key=…` |
| `/repair` | POST | Coordinate repair (`mode=light\|scan\|prune\|rebuild`) |
| `/repair/status` | GET | Current repair state + pending-writes queue depth |
| `/silent-save` | POST | Stop-hook save path with queue-and-drain during rebuild |
| `/mine` | POST | Bulk import a directory (validated absolute path only) |
| `/flush` | POST | Force checkpoint of pending writes |
| `/reload` | POST | Invalidate cached client + collection |
| `/backup` | POST | SQLite snapshot to a sibling file |
| `/mcp` | POST | MCP-protocol passthrough |

All endpoints honor `X-Api-Key` when `PALACE_API_KEY` is set.

## Development

```bash
# Smoke-test the running daemon
PALACE_DAEMON_URL=http://localhost:8085 PALACE_API_KEY=... scripts/verify-routes.sh

# One-command deploy (push + sync-wait + restart + verify)
scripts/deploy.sh

# Switch local Claude Code sessions between modes
palace-mode {status,local,remote [URL],install,verify}
```

## Sources

- [rboarescu/palace-daemon](https://github.com/rboarescu/palace-daemon) — upstream
- [MemPalace/mempalace](https://github.com/MemPalace/mempalace) — the underlying memory system this daemon fronts
- [jphein/mempalace](https://github.com/jphein/mempalace) — the production fork of mempalace this daemon is paired with
- [multipass-structural-memory-eval](https://github.com/M0nkeyFl0wer/multipass-structural-memory-eval) — the SME framework whose palace-daemon adapter consumes `/graph`
- [Apache AGE](https://age.apache.org/) — graph extension for postgres, candidate KG view technology if mempalace's KG ever justifies it (currently doesn't)
- [pgvector](https://github.com/pgvector/pgvector) — vector extension for postgres, candidate semantic-search view technology under upstream MemPalace [#665](https://github.com/MemPalace/mempalace/pull/665)
- [D3.js](https://d3js.org/) + [Mermaid](https://mermaid.js.org/) — `/viz` dashboard rendering, both via CDN, no bundler / no static-asset deps
- Upstream PRs that informed `/viz`: [#1022](https://github.com/MemPalace/mempalace/pull/1022) (D3 KG viz, sangeethkc), [#393](https://github.com/MemPalace/mempalace/pull/393) (Mermaid in docs, jravas), [#431](https://github.com/MemPalace/mempalace/pull/431) (CLI stats, MiloszPodsiadly), [#256](https://github.com/MemPalace/mempalace/pull/256) (sync_status MCP, rusel95), [#601](https://github.com/MemPalace/mempalace/pull/601) (brief overview, mvanhorn) — synthesized, not cherry-picked

## License

MIT — same as upstream.
