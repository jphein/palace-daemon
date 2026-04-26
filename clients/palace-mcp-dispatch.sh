#!/bin/bash
# Dispatches MCP server based on PALACE_DAEMON_URL env var.
#   set    → proxy to daemon (mempalace-mcp.py)
#   unset  → in-process mempalace.mcp_server (local palace)
#
# Resolve the sibling mempalace-mcp.py relative to this script (works
# when this dispatcher is invoked from a Claude Code plugin with
# CLAUDE_PLUGIN_ROOT or directly via an absolute path or symlink).

PYTHON="${MEMPALACE_PYTHON:-python3}"
HERE="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" &> /dev/null && pwd)"
MCP_CLIENT="$HERE/mempalace-mcp.py"

if [ -n "$PALACE_DAEMON_URL" ]; then
  exec "$PYTHON" "$MCP_CLIENT" --daemon "$PALACE_DAEMON_URL"
else
  exec "$PYTHON" -m mempalace.mcp_server
fi
