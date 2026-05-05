"""Unit tests for PALACE_DAEMON_PATH_MAP parsing + translation.

Run with::

    cd /path/to/palace-daemon
    python -m unittest tests.test_path_translation -v

These tests are pure-function and need no live daemon, palace, or
network. They exist because the path-translation logic is the only
glue between the hook's client-side path namespace and the daemon's
filesystem view; getting it wrong silently swallows transcript ingest.
"""
import os
import sys
import unittest
from unittest.mock import patch

# Ensure project root is on sys.path so ``import main`` resolves to the
# daemon's main.py regardless of where the test runner is invoked from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import main  # noqa: E402


class TestParsePathMap(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(main._parse_path_map(""), [])
        self.assertEqual(main._parse_path_map(None), [])
        self.assertEqual(main._parse_path_map("   "), [])

    def test_single_pair(self):
        out = main._parse_path_map("/home/u/.claude/=/mnt/raid/claude-config/")
        self.assertEqual(out, [("/home/u/.claude/", "/mnt/raid/claude-config/")])

    def test_multiple_pairs_preserve_order(self):
        raw = "/home/u/.claude/=/mnt/raid/cc/,/home/u/Projects/=/mnt/raid/projects/"
        out = main._parse_path_map(raw)
        self.assertEqual(
            out,
            [
                ("/home/u/.claude/", "/mnt/raid/cc/"),
                ("/home/u/Projects/", "/mnt/raid/projects/"),
            ],
        )

    def test_skips_malformed_entries(self):
        # Missing '=' and empty entries are skipped, valid ones survive.
        raw = "noequals,,/a/=/b/, =/x/, /c/= "
        out = main._parse_path_map(raw)
        self.assertEqual(out, [("/a/", "/b/")])

    def test_strips_whitespace_around_tokens(self):
        out = main._parse_path_map("  /a/  =  /b/  ")
        self.assertEqual(out, [("/a/", "/b/")])

    def test_reads_env_var_when_no_arg(self):
        with patch.dict(
            os.environ, {"PALACE_DAEMON_PATH_MAP": "/x/=/y/"}, clear=False
        ):
            out = main._parse_path_map()
        self.assertEqual(out, [("/x/", "/y/")])


class TestTranslateClientPath(unittest.TestCase):
    def test_passthrough_when_no_map(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                main._translate_client_path("/home/u/.claude/projects/-x"),
                "/home/u/.claude/projects/-x",
            )

    def test_first_matching_prefix_wins(self):
        env = {"PALACE_DAEMON_PATH_MAP": "/home/u/.claude/=/mnt/raid/cc/"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                main._translate_client_path("/home/u/.claude/projects/-x"),
                "/mnt/raid/cc/projects/-x",
            )

    def test_non_matching_path_passes_through(self):
        env = {"PALACE_DAEMON_PATH_MAP": "/home/u/.claude/=/mnt/raid/cc/"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                main._translate_client_path("/var/log/syslog"),
                "/var/log/syslog",
            )

    def test_multiple_rules_first_match_wins(self):
        # Order matters: list more specific rules first if needed.
        env = {
            "PALACE_DAEMON_PATH_MAP": (
                "/home/u/Projects/memorypalace/=/mnt/raid/mempalace/,"
                "/home/u/Projects/=/mnt/raid/projects/"
            )
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                main._translate_client_path("/home/u/Projects/memorypalace/foo"),
                "/mnt/raid/mempalace/foo",
            )
            self.assertEqual(
                main._translate_client_path("/home/u/Projects/realmwatch/foo"),
                "/mnt/raid/projects/realmwatch/foo",
            )


if __name__ == "__main__":
    unittest.main()
