"""Tests for /mine queue + drain during repair=rebuild.

Mirrors the silent-save queue contract: while a rebuild is in progress,
/mine requests are appended to a jsonl file at ``_pending_mines_path()``
and replayed by ``_drain_pending_mines()`` after the rebuild completes.

Run with::

    python -m unittest tests.test_mine_queue -v

Pure-function and pure-IO tests; no live daemon required. The drain
test stubs the chromadb subprocess invocation by monkey-patching
``asyncio.create_subprocess_exec``.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import main  # noqa: E402


class TestPendingMinesPath(unittest.TestCase):
    """The pending-mines file lives alongside the silent-save pending file
    but with a distinct name, so a daemon-busy save and a daemon-busy mine
    can both queue independently."""

    def test_path_is_separate_from_writes_path(self):
        # Both derive from _config.palace_path's parent, but the basenames differ.
        writes = main._pending_writes_path()
        mines = main._pending_mines_path()
        self.assertNotEqual(writes, mines)
        self.assertTrue(mines.endswith("palace-daemon-pending-mines.jsonl"))


class TestEnqueueAndDrain(unittest.IsolatedAsyncioTestCase):
    """End-to-end: enqueue a few payloads, then drain — verify dedup + replay."""

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Point the queue file inside the tmp dir
        self._queue_path = os.path.join(self.tmp.name, "pending-mines.jsonl")
        self._patches = [
            patch.object(main, "_pending_mines_path", return_value=self._queue_path),
            # Skip path translation for tests
            patch.object(main, "_translate_client_path", side_effect=lambda p: p),
        ]
        for p in self._patches:
            p.start()
        # Make every replayed dir "exist" so the drain doesn't skip
        self._is_dir_patch = patch("pathlib.Path.is_dir", return_value=True)
        self._is_dir_patch.start()

    async def asyncTearDown(self):
        for p in self._patches:
            p.stop()
        self._is_dir_patch.stop()
        self.tmp.cleanup()

    async def test_enqueue_then_drain_replays_each_target(self):
        await main._enqueue_pending_mine({"dir": "/a", "wing": "wa", "mode": "convos"})
        await main._enqueue_pending_mine({"dir": "/b", "wing": "wb", "mode": "convos"})
        self.assertTrue(os.path.isfile(self._queue_path))

        # Stub the subprocess: each call returns rc=0
        async def _fake_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_subprocess) as spawn:
            count = await main._drain_pending_mines()
        self.assertEqual(count, 2)
        # Queue file is gone after a clean drain
        self.assertFalse(os.path.isfile(self._queue_path))
        # Subprocess was invoked twice (once per unique target)
        self.assertEqual(spawn.call_count, 2)

    async def test_drain_dedups_repeated_target(self):
        """A storm of hook fires queues the same (dir, wing, mode) many times.
        Drain replays once per unique target — a single mine catches up all
        the queued requests via convo_miner's mtime-based dedup anyway."""
        for _ in range(10):
            await main._enqueue_pending_mine({"dir": "/a", "wing": "wa", "mode": "convos"})

        async def _fake_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_subprocess) as spawn:
            count = await main._drain_pending_mines()
        self.assertEqual(count, 1)
        self.assertEqual(spawn.call_count, 1)

    async def test_drain_quarantines_failed_replays(self):
        """A non-zero subprocess exit doesn't lose the queue entry — it
        moves to a timestamped .failed-* file so the next drain doesn't
        replay it again."""
        await main._enqueue_pending_mine({"dir": "/a", "wing": "wa", "mode": "convos"})

        async def _fake_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b"boom"))
            proc.returncode = 1
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_subprocess):
            count = await main._drain_pending_mines()
        self.assertEqual(count, 0)
        # Original queue file was removed; a .failed-* sibling exists
        self.assertFalse(os.path.isfile(self._queue_path))
        siblings = os.listdir(self.tmp.name)
        failed = [s for s in siblings if ".failed-" in s]
        self.assertEqual(len(failed), 1)

    async def test_drain_empty_queue_returns_zero(self):
        """No queue file → no work → return 0, no error."""
        count = await main._drain_pending_mines()
        self.assertEqual(count, 0)

    async def test_drain_replays_extract_and_limit_options(self):
        """Closes Copilot finding on jphein/palace-daemon#4 — drain
        previously dropped optional ``extract`` / ``limit`` fields,
        so a queue entry that included them got replayed without."""
        await main._enqueue_pending_mine({
            "dir": "/a", "wing": "wa", "mode": "convos",
            "extract": "exchange", "limit": 100,
        })

        captured_argv = []

        async def _fake_subprocess(*args, **kwargs):
            captured_argv.append(list(args))
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_subprocess):
            count = await main._drain_pending_mines()

        self.assertEqual(count, 1)
        self.assertEqual(len(captured_argv), 1)
        argv = captured_argv[0]
        # extract and limit make it onto the replay command
        self.assertIn("--extract", argv)
        self.assertEqual(argv[argv.index("--extract") + 1], "exchange")
        self.assertIn("--limit", argv)
        self.assertEqual(argv[argv.index("--limit") + 1], "100")

    async def test_drain_replays_session_mode(self):
        """Regression for Copilot finding on jphein/palace-daemon#5 — the
        drain's local VALID_MODES had drifted to {convos, projects},
        silently dropping queued ``session`` mines that the live /mine
        endpoint accepts. Both paths now share _MINE_VALID_MODES."""
        self.assertIn("session", main._MINE_VALID_MODES)
        await main._enqueue_pending_mine({"dir": "/a", "wing": "wa", "mode": "session"})

        captured_argv = []

        async def _fake_subprocess(*args, **kwargs):
            captured_argv.append(list(args))
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_subprocess):
            count = await main._drain_pending_mines()

        self.assertEqual(count, 1, "session-mode mine must survive the drain")
        argv = captured_argv[0]
        self.assertEqual(argv[argv.index("--mode") + 1], "session")

    async def test_drain_skips_invalid_payload_fields(self):
        """Closes Copilot finding on jphein/palace-daemon#4 — drain
        previously skipped only is_dir() check; now also enforces
        the same valid-mode / valid-extract / int-limit / no-traversal
        guards as the live /mine endpoint."""
        for bad in (
            {"dir": "../../etc/passwd", "wing": "wa", "mode": "convos"},  # traversal
            {"dir": "/a", "wing": "wa", "mode": "wrong-mode"},  # invalid mode
            {"dir": "/a", "wing": "wa", "mode": "convos", "extract": "wrong"},  # invalid extract
            {"dir": "/a", "wing": "wa", "mode": "convos", "limit": "not-a-number"},  # invalid limit
            {"dir": None, "wing": "wa", "mode": "convos"},  # invalid dir type
        ):
            await main._enqueue_pending_mine(bad)

        async def _fake_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_fake_subprocess) as spawn:
            count = await main._drain_pending_mines()
        # All five entries skipped, no subprocess spawned, count = 0
        self.assertEqual(count, 0)
        self.assertEqual(spawn.call_count, 0)


if __name__ == "__main__":
    unittest.main()


class TestMineablePath:
    """/mine and the drain path accept a directory OR a single .jsonl transcript.

    Hooks post one transcript per checkpoint (mempalace#414/#426); posting the
    parent directory re-mined the whole project every time.
    """

    def test_directory_is_mineable(self, tmp_path):
        from main import _is_mineable_path

        assert _is_mineable_path(tmp_path) is True

    def test_jsonl_file_is_mineable(self, tmp_path):
        from main import _is_mineable_path

        f = tmp_path / "session.jsonl"
        f.write_text("{}\n")
        assert _is_mineable_path(f) is True

    def test_other_file_is_not_mineable(self, tmp_path):
        from main import _is_mineable_path

        f = tmp_path / "notes.txt"
        f.write_text("x")
        assert _is_mineable_path(f) is False

    def test_missing_path_is_not_mineable(self, tmp_path):
        from main import _is_mineable_path

        assert _is_mineable_path(tmp_path / "nope.jsonl") is False


class TestDrainRequeuesOnLockContention(unittest.IsolatedAsyncioTestCase):
    """A replay that fails only because another process holds the palace
    flock is requeued for the next pass, not quarantined (a sweep running
    while hooks post would otherwise silently drop every ingest)."""

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._queue_path = os.path.join(self.tmp.name, "pending-mines.jsonl")
        self._patches = [
            patch.object(main, "_pending_mines_path", return_value=self._queue_path),
            patch.object(main, "_translate_client_path", side_effect=lambda p: p),
            patch("pathlib.Path.is_dir", return_value=True),
            patch.object(main, "_LOCK_REQUEUE_DELAY_S", 0),
        ]
        for p in self._patches:
            p.start()

    async def asyncTearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    async def test_lock_held_is_requeued_not_quarantined(self):
        await main._enqueue_pending_mine({"dir": "/a", "wing": "wa", "mode": "convos"})

        async def _spawn(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(
                return_value=(b"", b"mempalace: palace /p is held by PID 42 (mine); wait for it")
            )
            proc.returncode = 1
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_spawn):
            drained = await main._drain_pending_mines()
        self.assertEqual(drained, 0)
        self.assertTrue(os.path.isfile(self._queue_path), "entry must be back on the live queue")
        with open(self._queue_path) as f:
            entry = json.loads(f.read().strip())
        self.assertEqual(entry["lock_retries"], 1)
        self.assertEqual(entry["payload"]["dir"], "/a")
        failed = [n for n in os.listdir(self.tmp.name) if ".failed-" in n]
        self.assertEqual(failed, [], "lock contention must not quarantine")

    async def test_gives_up_after_max_retries(self):
        await main._enqueue_pending_mine({"dir": "/a", "wing": "wa", "mode": "convos"})
        # pre-set the retry counter at the ceiling
        with open(self._queue_path) as f:
            entry = json.loads(f.read().strip())
        entry["lock_retries"] = main._LOCK_REQUEUE_MAX
        with open(self._queue_path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        async def _spawn(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b"palace /p is held by PID 42"))
            proc.returncode = 1
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_spawn):
            await main._drain_pending_mines()
        self.assertFalse(os.path.isfile(self._queue_path))
        failed = [n for n in os.listdir(self.tmp.name) if ".failed-" in n]
        self.assertEqual(len(failed), 1, "exhausted retries are quarantined")


class TestRecoverOrphanedProcessing(unittest.IsolatedAsyncioTestCase):
    """An interrupted drain batch (.processing left behind by a restart) is
    folded back into the live queue and drained, not stranded forever."""

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._queue_path = os.path.join(self.tmp.name, "pending-mines.jsonl")
        self._patches = [
            patch.object(main, "_pending_mines_path", return_value=self._queue_path),
            patch.object(main, "_translate_client_path", side_effect=lambda p: p),
            patch("pathlib.Path.is_dir", return_value=True),
        ]
        for p in self._patches:
            p.start()

    async def asyncTearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    async def test_orphaned_batch_is_recovered_and_drained(self):
        orphan = self._queue_path + ".processing"
        with open(orphan, "w") as f:
            f.write(json.dumps({"payload": {"dir": "/a", "wing": "wa", "mode": "convos"}}) + "\n")

        async def _spawn(*args, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_spawn) as spawn:
            drained = await main._drain_pending_mines()
        self.assertEqual(drained, 1)
        spawn.assert_called_once()
        self.assertFalse(os.path.exists(orphan))
        self.assertFalse(os.path.exists(self._queue_path))

    def test_recover_returns_zero_when_nothing_orphaned(self):
        self.assertEqual(
            main._recover_orphaned_processing(self._queue_path, self._queue_path + ".processing"), 0
        )


class TestMineStatusEndpoint(unittest.IsolatedAsyncioTestCase):
    """GET /mine/status reports queue depth, processing batch, active mines, drainer state."""

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._queue_path = os.path.join(self.tmp.name, "pending-mines.jsonl")
        self._patches = [
            patch.object(main, "_pending_mines_path", return_value=self._queue_path),
            patch.object(main, "_check_auth", side_effect=lambda *_a, **_k: None),
        ]
        for p in self._patches:
            p.start()
        main._mine_drain_task = None

    async def asyncTearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    async def test_reports_counts_and_peek(self):
        await main._enqueue_pending_mine({"dir": "/a.jsonl", "wing": "wa", "mode": "convos"})
        await main._enqueue_pending_mine({"dir": "/b.jsonl", "wing": "wb", "mode": "convos"})
        with open(self._queue_path + ".processing", "w") as f:
            f.write(json.dumps({"payload": {"dir": "/c.jsonl", "wing": "wc", "mode": "convos"}}) + "\n")
        main.app.state.active_mines = {object()}
        try:
            out = await main.mine_status(x_api_key=None)
        finally:
            main.app.state.active_mines = set()
        self.assertEqual(out["queued"], 2)
        self.assertEqual(out["processing"], 1)
        self.assertEqual(out["active_mines"], 1)
        self.assertFalse(out["drainer_running"])
        self.assertEqual([n["dir"] for n in out["next"]], ["/a.jsonl", "/b.jsonl", "/c.jsonl"])

    async def test_empty_queue(self):
        out = await main.mine_status(x_api_key=None)
        self.assertEqual((out["queued"], out["processing"], out["next"]), (0, 0, []))
