"""_default_peer_writer_env: postgres gets the peer-writer bypass by default.

mempalace v3.7 gates its multi-process-writer exemption behind
MEMPALACE_MCP_ALLOW_PEER_WRITER; without it the daemon's embedded MCP
server contends on the palace flock with the mine subprocesses the
daemon itself spawns (2026-08-09 incident: every Stop-hook diary
checkpoint refused while a long mine ran).
"""
import os
import sys
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import main  # noqa: E402


class TestPeerWriterEnvDefault(unittest.TestCase):
    def test_postgres_defaults_env_on(self):
        with patch.dict(os.environ, {"MEMPALACE_BACKEND": "postgres"}, clear=False):
            os.environ.pop("MEMPALACE_MCP_ALLOW_PEER_WRITER", None)
            main._default_peer_writer_env()
            self.assertEqual(os.environ.get("MEMPALACE_MCP_ALLOW_PEER_WRITER"), "1")

    def test_operator_override_wins(self):
        with patch.dict(
            os.environ,
            {"MEMPALACE_BACKEND": "postgres", "MEMPALACE_MCP_ALLOW_PEER_WRITER": "0"},
            clear=False,
        ):
            main._default_peer_writer_env()
            self.assertEqual(os.environ.get("MEMPALACE_MCP_ALLOW_PEER_WRITER"), "0")

    def test_non_postgres_backend_untouched(self):
        with patch.dict(os.environ, {"MEMPALACE_BACKEND": "chroma"}, clear=False):
            os.environ.pop("MEMPALACE_MCP_ALLOW_PEER_WRITER", None)
            main._default_peer_writer_env()
            self.assertIsNone(os.environ.get("MEMPALACE_MCP_ALLOW_PEER_WRITER"))


if __name__ == "__main__":
    unittest.main()
