#!/usr/bin/env bash
# palace-memory-sweep.sh [<project-dir-basename> ...]
# Re-index per-project ~/.claude/projects/<proj>/memory/*.md into the palace
# wing for that project. With no args, sweeps every project dir.
#
# ROUTES THROUGH THE DAEMON (POST /mine background=true), NOT a direct CLI
# mine. A direct `mempalace mine` takes the palace flock non-blocking and
# EXITS the instant another mine (the live transcript drainer, most of the
# time) holds it — so hook-triggered re-indexes silently did nothing whenever
# the palace was busy (fleet finding, sconce-17, 2026-09-03: a fact written
# and "re-indexed" was unretrievable because the mine bailed on the lock).
# The daemon queues the request and its drainer serializes + requeues on
# lock-held (up to 30×20s), so the write→index step is reliable.
set -u
set -a; source ~/.config/palace-daemon/env 2>/dev/null; set +a
DAEMON="${PALACE_DAEMON_URL:-http://127.0.0.1:8085}"
LOG=/var/tmp/ftarget/palace-memory-sweep.log
mkdir -p /var/tmp/ftarget
wing_for() {  # -home-jp-Projects-foo-bar -> foo_bar ; -home-jp -> jp ; -home-jp-Projects -> projects ; -home-jp-lights -> lights
  local b="$1"
  case "$b" in
    -home-jp) printf '%s' jp;;
    -home-jp-Projects) printf '%s' projects;;
    -home-jp-Projects-*) printf '%s' "${b#-home-jp-Projects-}" | tr 'A-Z-' 'a-z_';;
    -home-jp-*) printf '%s' "${b#-home-jp-}" | tr 'A-Z-' 'a-z_';;
    *) printf '%s' "$b" | tr 'A-Z-' 'a-z_';;
  esac
}
if [ $# -gt 0 ]; then dirs=("$@"); else
  mapfile -t dirs < <(find ~/.claude/projects -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
fi
ok=0; skip=0; fail=0
for b in "${dirs[@]}"; do
  d="$HOME/.claude/projects/$b/memory"
  [ -d "$d" ] || { skip=$((skip+1)); continue; }
  n=$(find "$d" -maxdepth 1 -name '*.md' | wc -l); [ "$n" -gt 0 ] || { skip=$((skip+1)); continue; }
  w=$(wing_for "$b")
  printf '[%s] queue %s -> wing=%s (%s files)\n' "$(date -Is)" "$b" "$w" "$n" >> "$LOG"
  body=$(printf '{"dir":"%s","wing":"%s","mode":"projects","background":true}' "$d" "$w")
  code=$(curl -s -m 20 -o /tmp/pms-resp.$$ -w '%{http_code}' -X POST "$DAEMON/mine" \
           -H "Content-Type: application/json" -H "X-API-Key: ${PALACE_API_KEY:-}" -d "$body")
  if [ "$code" = "200" ] || [ "$code" = "202" ]; then ok=$((ok+1)); printf '  -> %s %s\n' "$code" "$(head -c 160 /tmp/pms-resp.$$)" >> "$LOG"
  else fail=$((fail+1)); printf '[%s] FAILED %s http=%s %s\n' "$(date -Is)" "$b" "$code" "$(head -c 200 /tmp/pms-resp.$$)" >> "$LOG"; fi
  rm -f /tmp/pms-resp.$$
done
printf '[%s] sweep queued ok=%s skip=%s fail=%s (daemon drains in background; GET /mine/status)\n' "$(date -Is)" "$ok" "$skip" "$fail" | tee -a "$LOG"
