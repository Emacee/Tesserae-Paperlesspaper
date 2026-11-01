"""Unit tests for energy_dynamic_price/server.py. Network is mocked.

Run standalone:  python -m unittest discover -s energy_dynamic_price/tests
(pytest picks these up too).
"""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_edp_server", _HERE / "server.py")
assert _spec and _spec.loader
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

# 2026-11-01 12:05 Amsterdam (CET, UTC+1).
NOW = datetime(2026, 11, 1, 11, 5, tzinfo=timezone.utc)


def _ez_payload(first_local_day: str, days: int) -> bytes:
    """EnergyZero-shaped payload: ``days`` days of quarter slots, CET."""
    start = datetime.fromisoformat(first_local_day + "T00:00:00+01:00").astimezone(timezone.utc)
    rows = []
    for k in range(96 * days):
        s = start + timedelta(minutes=15 * k)
        # 0.30 €/kWh baseline, cheap dip at 03:00, peak at 18:00.
        hour = (k % 96) / 4
        eur = 0.30 + (0.20 if 18 <= hour < 19 else 0) - (0.10 if 3 <= hour < 4 else 0)
        rows.append({
            "start": s.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (s + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price": {"value": f"{eur:.5f}"},
        })
    return json.dumps({"interval": "RESPONSE_INTERVAL_QUARTER", "all_in_with_vat": rows,
                       "base": rows}).encode()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http404(url):
    return urllib.error.HTTPError(url, 404, "Not Found", {}, None)


class EnergyZeroTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = {"data_dir": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_tomorrow_not_published_falls_back_to_today(self):
        calls = []

        def fake(req, timeout=None):
            calls.append(req.full_url)
            if "date=02-11-2026" in req.full_url:
                raise _http404(req.full_url)
            return _Resp(_ez_payload("2026-10-31", 2))

        with patch("urllib.request.urlopen", side_effect=fake):
            d = server.fetch({}, {}, ctx=self.ctx, now=NOW)
        self.assertNotIn("error", d)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(d["slots"]), 96)
        self.assertFalse(d["has_tomorrow"])
        self.assertEqual(d["minutes"], 15)
        self.assertEqual(d["now"]["from"], "12:00")
        self.assertEqual(d["now"]["till"], "12:15")
        self.assertAlmostEqual(d["now"]["p"], 30.0)
        # Upcoming-only stats: 03:00 dip is past, so lowest is "now"-level.
        self.assertEqual(d["max"]["t"], "18:00")
        self.assertAlmostEqual(d["max"]["p"], 50.0)
        self.assertAlmostEqual(d["min"]["p"], 30.0)

    def test_today_and_tomorrow(self):
        with patch("urllib.request.urlopen", return_value=_Resp(_ez_payload("2026-11-01", 2))):
            d = server.fetch({}, {}, ctx=self.ctx, now=NOW)
        self.assertTrue(d["has_tomorrow"])
        self.assertEqual(len(d["slots"]), 192)
        self.assertEqual([x["key"] for x in d["days"]], ["today", "tomorrow"])
        self.assertEqual(d["days"][1]["i"], 96)
        self.assertEqual(d["min"]["day"], "tomorrow")
        self.assertEqual(d["min"]["t"], "03:00")
        self.assertAlmostEqual(d["min"]["p"], 20.0)

    def test_window_scope_includes_past(self):
        with patch("urllib.request.urlopen", return_value=_Resp(_ez_payload("2026-10-31", 2))):
            d = server.fetch({"stats_scope": "window"}, {}, ctx=self.ctx, now=NOW)
        self.assertEqual(d["min"]["t"], "03:00")
        self.assertEqual(d["min"]["day"], "today")

    def test_ahead_starts_at_now(self):
        with patch("urllib.request.urlopen", return_value=_Resp(_ez_payload("2026-11-01", 2))):
            d = server.fetch({"range": "ahead"}, {}, ctx=self.ctx, now=NOW)
        self.assertEqual(d["slots"][0]["t"], "12:00")
        self.assertEqual(d["now"]["i"], 0)

    def test_cache_hit_skips_network(self):
        with patch("urllib.request.urlopen", return_value=_Resp(_ez_payload("2026-11-01", 2))):
            server.fetch({}, {}, ctx=self.ctx, now=NOW)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            d = server.fetch({}, {}, ctx=self.ctx, now=NOW + timedelta(minutes=5))
        self.assertEqual(d["now"]["from"], "12:00")

    def test_unreachable_is_friendly(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("dns")):
            d = server.fetch({}, {}, ctx=self.ctx, now=NOW)
        self.assertIn("unreachable", d["error"])


class TibberTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = {"data_dir": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_token(self):
        d = server.fetch({"source": "tibber"}, {}, ctx=self.ctx, now=NOW)
        self.assertIn("token", d["error"])

    def test_prices_and_auth_header(self):
        today = [
            {"total": 0.40 + (0.1 if h == 18 else 0), "currency": "EUR",
             "startsAt": f"2026-11-01T{h:02d}:00:00.000+01:00"}
            for h in range(24)
        ]
        payload = {"data": {"viewer": {"homes": [
            {"id": "x", "currentSubscription": None},
            {"id": "h1", "currentSubscription": {"priceInfo": {"today": today, "tomorrow": []}}},
        ]}}}
        seen = {}

        def fake(req, timeout=None):
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data)
            return _Resp(json.dumps(payload).encode())

        with patch("urllib.request.urlopen", side_effect=fake):
            d = server.fetch({"source": "tibber", "resolution": "60"},
                             {"tibber_token": "abc"}, ctx=self.ctx, now=NOW)
        self.assertEqual(seen["auth"], "Bearer abc")
        self.assertEqual(seen["body"]["variables"]["res"], "HOURLY")
        self.assertEqual(d["minutes"], 60)
        self.assertEqual(d["unit"], "ct")
        self.assertEqual(d["now"]["from"], "12:00")
        self.assertAlmostEqual(d["max"]["p"], 50.0)

    def test_bad_token_is_friendly(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)):
            d = server.fetch({"source": "tibber"}, {"tibber_token": "bad"}, ctx=self.ctx, now=NOW)
        self.assertIn("rejected", d["error"])


if __name__ == "__main__":
    unittest.main()
