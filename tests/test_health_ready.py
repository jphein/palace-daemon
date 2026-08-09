"""Tests for /health/ready — search-path readiness (mempalace#384).

The 2026-07..08 searcher outage (UnboundLocalError on every hybrid
search) was invisible to monitoring because /health only opens the
collection — it never exercises the query path. /health/ready runs the
real mempalace_search MCP tool and reports ready/failing.

Contract locked in here:

- 200 + status="ready" when the probe's _call returns a result envelope
- 503 + status="failing" + error_code when it returns an error envelope
  (the exact shape production produced during the outage)
- the response NEVER carries search results or error message text —
  the endpoint is keyless, so content must not leak
- results are cached for PALACE_READY_TTL_SECONDS: polls inside the
  window reuse the probe instead of re-searching

Run with::

    cd /home/jp/Projects/palace-daemon
    venv/bin/python -m pytest tests/test_health_ready.py -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import main  # noqa: E402

_SUCCESS_ENVELOPE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {"content": [{"type": "text", "text": json.dumps({
        "results": [{"text": "SECRET DRAWER CONTENT", "wing": "general"}],
    })}]},
}

# The production failure shape from mempalace#378/#384: the MCP layer
# folds the searcher's UnboundLocalError into a -32000 error envelope.
_ERROR_ENVELOPE = {
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32000,
        "message": (
            "Tool error in mempalace_search: UnboundLocalError: cannot access "
            "local variable 'lexical' where it is not associated with a value"
        ),
    },
}


def _fresh_cache():
    return {"at": 0.0, "ok": None, "error_code": None, "latency_ms": None}


class TestHealthReady(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Every test starts with an expired cache.
        self._cache_patch = patch.object(main, "_ready_cache", _fresh_cache())
        self._cache_patch.start()

    def tearDown(self):
        self._cache_patch.stop()

    def _unwrap(self, resp):
        if isinstance(resp, dict):
            return 200, resp
        return resp.status_code, json.loads(resp.body)

    async def test_ready_when_search_succeeds(self):
        with patch.object(main, "_call", AsyncMock(return_value=_SUCCESS_ENVELOPE)) as call:
            resp = await main.health_ready()
        code, body = self._unwrap(resp)
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["probe"], "mempalace_search")
        call.assert_awaited_once()
        # The probe must exercise the real tool path.
        request = call.await_args.args[0]
        self.assertEqual(request["params"]["name"], "mempalace_search")
        self.assertEqual(request["params"]["arguments"]["limit"], 1)

    async def test_failing_when_search_returns_error_envelope(self):
        """The exact mempalace#384 outage shape → 503, externally visible."""
        with patch.object(main, "_call", AsyncMock(return_value=_ERROR_ENVELOPE)):
            resp = await main.health_ready()
        code, body = self._unwrap(resp)
        self.assertEqual(code, 503)
        self.assertEqual(body["status"], "failing")
        self.assertEqual(body["error_code"], -32000)

    async def test_no_content_or_message_leakage(self):
        """Keyless endpoint: neither drawer text nor error text may appear."""
        for envelope in (_SUCCESS_ENVELOPE, _ERROR_ENVELOPE):
            main._ready_cache.update(_fresh_cache())
            with patch.object(main, "_call", AsyncMock(return_value=envelope)):
                resp = await main.health_ready()
            _, body = self._unwrap(resp)
            serialized = json.dumps(body)
            self.assertNotIn("SECRET DRAWER CONTENT", serialized)
            self.assertNotIn("UnboundLocalError", serialized)
            self.assertNotIn("results", body)

    async def test_probe_exception_reports_failing(self):
        with patch.object(main, "_call", AsyncMock(side_effect=RuntimeError("boom"))):
            resp = await main.health_ready()
        code, body = self._unwrap(resp)
        self.assertEqual(code, 503)
        self.assertEqual(body["status"], "failing")
        self.assertNotIn("boom", json.dumps(body))

    async def test_probe_result_is_cached_within_ttl(self):
        with patch.object(main, "_call", AsyncMock(return_value=_SUCCESS_ENVELOPE)) as call:
            first = await main.health_ready()
            second = await main.health_ready()
        call.assert_awaited_once()  # one probe, two responses
        _, body1 = self._unwrap(first)
        _, body2 = self._unwrap(second)
        self.assertFalse(body1["cached"])
        self.assertTrue(body2["cached"])

    async def test_cache_expiry_reprobes(self):
        with patch.object(main, "_call", AsyncMock(return_value=_SUCCESS_ENVELOPE)) as call, \
             patch.object(main, "PALACE_READY_TTL_SECONDS", 0.0):
            await main.health_ready()
            await main.health_ready()
        self.assertEqual(call.await_count, 2)


if __name__ == "__main__":
    unittest.main()
