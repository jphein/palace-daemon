"""Tests for the truthful Stop-hook save summary (techempower-org/mempalace#382).

Locks in the three fixes:

  (a) the hook.log summary reports diary and mine outcomes SEPARATELY —
      the pre-fix line said "Silent save (diary+mine) OK" even when the
      transcript mine had just failed (8,218 mine failures logged under
      a healthy-looking summary);
  (b) a client-side /mine timeout is distinguished from a hard failure —
      the daemon may still land the ingest after the hook gives up, so
      the summary says so instead of claiming a clean failure;
  (c) the precompact MEMPAL_DIR mine honors the ``mine_timeout_s`` knob
      instead of a hardcoded ``timeout=60``.

Everything is mocked — no real daemon, no fork.

Run with::

    cd /home/jp/Projects/palace-daemon
    PYTHONPATH=. venv/bin/python -m pytest tests/test_hook_save_summary.py -q
"""
import os
import sys
import unittest
from unittest.mock import patch

# Ensure clients/ is on sys.path so `import hook` resolves.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CLIENTS = os.path.join(os.path.dirname(_HERE), "clients")
if _CLIENTS not in sys.path:
    sys.path.insert(0, _CLIENTS)

import hook  # noqa: E402


class TestComposeSaveSummary(unittest.TestCase):
    """The summary line reflects each sub-operation's actual outcome."""

    def test_both_ok(self):
        line = hook._compose_save_summary(True, {"status": "ok"}, 15, "mempalace")
        self.assertIn("diary OK", line)
        self.assertIn("mine OK", line)
        self.assertIn("exchange 15", line)
        self.assertIn("mempalace", line)

    def test_diary_ok_mine_timeout_is_not_reported_as_ok(self):
        # The exact #382 scenario: mine timed out, diary succeeded. The
        # pre-fix summary said "(diary+mine) OK" here.
        outcome = {"status": "timeout",
                   "detail": "network/transport: The read operation timed out"}
        line = hook._compose_save_summary(True, outcome, 30, "mempalace")
        self.assertIn("diary OK", line)
        self.assertIn("mine TIMED OUT", line)
        self.assertIn("may still complete server-side", line)
        self.assertNotIn("mine OK", line)

    def test_diary_failed_mine_ok(self):
        line = hook._compose_save_summary(False, {"status": "ok"}, 45, "general")
        self.assertIn("diary FAILED", line)
        self.assertIn("mine OK", line)

    def test_hard_failure_reports_detail_and_journal(self):
        outcome = {"status": "failed", "detail": "HTTP 500"}
        line = hook._compose_save_summary(True, outcome, 60, "general")
        self.assertIn("mine FAILED (HTTP 500", line)
        self.assertIn("journaled for replay", line)
        self.assertNotIn("TIMED OUT", line)


class TestIngestOutcomeOut(unittest.TestCase):
    """_ingest_with_wake_and_journal populates outcome_out truthfully."""

    def test_success_reports_ok(self):
        with patch.object(hook, "_ingest_transcript_via_daemon", return_value=True):
            outcome = {}
            ok = hook._ingest_with_wake_and_journal(
                "http://d:8085", "/tmp/t.jsonl", "w", "s", outcome_out=outcome)
        self.assertTrue(ok)
        self.assertEqual(outcome["status"], "ok")

    def test_timeout_reports_timeout_status(self):
        def fake_ingest(daemon_url, tp, wing, failure_out=None):
            if failure_out is not None:
                failure_out["error"] = "network/transport: timed out"
                failure_out["eligible"] = False
            return False

        with patch.object(hook, "_ingest_transcript_via_daemon", fake_ingest), \
             patch.object(hook, "_journal_failed_ingest") as journal:
            outcome = {}
            ok = hook._ingest_with_wake_and_journal(
                "http://d:8085", "/tmp/t.jsonl", "w", "s", outcome_out=outcome)
        self.assertFalse(ok)
        self.assertEqual(outcome["status"], "timeout")
        self.assertIn("timed out", outcome["detail"])
        journal.assert_called_once()

    def test_hard_failure_reports_failed_status(self):
        def fake_ingest(daemon_url, tp, wing, failure_out=None):
            if failure_out is not None:
                failure_out["error"] = "HTTP 500 Internal Server Error"
                failure_out["eligible"] = False
            return False

        with patch.object(hook, "_ingest_transcript_via_daemon", fake_ingest), \
             patch.object(hook, "_journal_failed_ingest"):
            outcome = {}
            ok = hook._ingest_with_wake_and_journal(
                "http://d:8085", "/tmp/t.jsonl", "w", "s", outcome_out=outcome)
        self.assertFalse(ok)
        self.assertEqual(outcome["status"], "failed")

    def test_bool_only_contract_still_works(self):
        # Existing callers pass no outcome_out; the bool contract holds.
        with patch.object(hook, "_ingest_transcript_via_daemon", return_value=True):
            self.assertTrue(hook._ingest_with_wake_and_journal(
                "http://d:8085", "/tmp/t.jsonl", "w", "s"))


class TestTimeoutClassifier(unittest.TestCase):
    def test_timeout_strings(self):
        self.assertTrue(hook._is_timeout_error("network/transport: timed out"))
        self.assertTrue(hook._is_timeout_error(
            "network/transport: The read operation timed out"))
        self.assertTrue(hook._is_timeout_error("connect timeout"))

    def test_non_timeout_strings(self):
        self.assertFalse(hook._is_timeout_error("HTTP 500 Internal Server Error"))
        self.assertFalse(hook._is_timeout_error("Connection refused"))
        self.assertFalse(hook._is_timeout_error("unknown"))


class TestPrecompactTimeoutKnob(unittest.TestCase):
    """The MEMPAL_DIR mine in hook_precompact honors mine_timeout_s."""

    def _drive_precompact(self, settings):
        import io
        calls = []

        def spy_post_mine(daemon_url, mine_dir, timeout=60, mode="convos",
                          wing="", label="mine"):
            calls.append({"dir": mine_dir, "timeout": timeout,
                          "mode": mode, "label": label})
            return False, {"error": "stub"}

        data = {"session_id": "precompact-knob-test",
                "transcript_path": "/tmp/does-not-exist.jsonl"}
        with patch.object(hook, "_load_hook_settings", return_value=settings), \
             patch.object(hook, "_post_mine", spy_post_mine), \
             patch.object(hook, "_get_palace_stats", return_value={}), \
             patch.object(hook, "_get_mine_dir", return_value="/tmp/mine-dir"), \
             patch.object(hook, "_ingest_with_wake_and_journal", return_value=True), \
             patch.object(hook, "_detach_for_async_work", return_value=True), \
             patch.object(hook, "_desktop_notify"), \
             patch("sys.stdout", new=io.StringIO()):
            hook.hook_precompact(data, "claude-code")
        return calls

    def test_mempal_dir_mine_uses_knob(self):
        calls = self._drive_precompact({"mine_timeout_s": 180})
        mempal = [c for c in calls if c["dir"] == "/tmp/mine-dir"]
        self.assertEqual(len(mempal), 1)
        self.assertEqual(mempal[0]["timeout"], 180,
                         "MEMPAL_DIR mine must honor mine_timeout_s")

    def test_mempal_dir_mine_defaults_to_60(self):
        calls = self._drive_precompact({})
        mempal = [c for c in calls if c["dir"] == "/tmp/mine-dir"]
        self.assertEqual(len(mempal), 1)
        self.assertEqual(mempal[0]["timeout"], 60)


if __name__ == "__main__":
    unittest.main()
