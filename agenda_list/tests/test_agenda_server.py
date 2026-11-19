"""agenda_list: offline, with fake Calendar Core and Home Assistant Core.
The events, places and drive times here are made up."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agenda_list_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]

AMS = ZoneInfo("Europe/Amsterdam")
TZ = {"timezone": "Europe/Amsterdam"}
NOW = datetime(2026, 11, 19, 6, 0, tzinfo=AMS)


class FakeCal:
    data_dir = "."

    def __init__(self, events):
        self.events = events
        self.server_module = self

    def load_events(self, feeds, start, end, *, data_dir=None):
        return self.events


class FakeCore:
    def __init__(self, minutes=30.2, fail=False):
        self.minutes, self.fail, self.calls = minutes, fail, []

    def call_service_with_response(self, domain, service, *, data=None, timeout=10):
        self.calls.append((domain, service, data))
        if self.fail:
            raise RuntimeError("no route")
        return {"service_response": {"routes": [{"duration": self.minutes + 9}, {"duration": self.minutes}]}}


def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=AMS).astimezone(S.timezone.utc).isoformat()


def ev(day, h, title, loc="", dur=1):
    return {"summary": title, "start": utc(2026, 11, day, h), "end": utc(2026, 11, day, h + dur), "all_day": False,
            "location": loc, "feed_colour": "#f900f4", "feed_symbol": "🏡"}


def run(events, core=None, **opts):
    S._cache.clear()
    return S._fetch({"timezone": "Europe/Amsterdam", **opts}, {}, ctx={}, now=NOW, cal=FakeCal(events), core=core if core is not None else FakeCore())


def test_drive_and_time_to_leave_with_margin():
    core = FakeCore(minutes=34.2)
    out = run([ev(19, 19, "Tennis", "Court 1")], core=core)
    e = out["days"][0]["events"][0]
    assert e["travel"] == {"min": 35, "leave": "18:20"}  # 19:00 - 35 - 5
    assert out["travel"] == "ok"
    assert core.calls[0][:2] == ("waze_travel_time", "get_travel_times")
    assert core.calls[0][2]["origin"] == "zone.home" and core.calls[0][2]["destination"] == "Court 1"


def test_margin_origin_and_region_are_options():
    core = FakeCore(minutes=10)
    out = run([ev(20, 10, "Lunch", "Cafe")], core=core, margin_min=15, origin="52.1,5.1", region="US")
    assert out["days"][1]["events"][0]["travel"]["leave"] == "09:35"
    assert core.calls[0][2]["origin"] == "52.1,5.1" and core.calls[0][2]["region"] == "us"


def test_region_goes_to_home_assistant_in_lower_case():
    core = FakeCore()
    run([ev(20, 10, "Lunch", "Cafe")], core=core, region="EU")
    assert core.calls[0][2]["region"] == "eu"


def test_no_location_or_past_event_asks_nothing():
    core = FakeCore()
    out = run([ev(19, 5, "Early", "Somewhere"), ev(19, 9, "No place")], core=core)
    assert core.calls == []
    assert all("travel" not in e for e in out["days"][0]["events"])


def test_answers_are_cached_and_failures_remembered():
    core = FakeCore()
    S._cache.clear()
    events = [ev(20, 9, "A", "Same place"), ev(21, 9, "B", "same place ")]
    S._fetch(TZ, {}, ctx={}, now=NOW, cal=FakeCal(events), core=core)
    S._fetch(TZ, {}, ctx={}, now=NOW, cal=FakeCal(events), core=core)
    assert len(core.calls) == 1
    bad = FakeCore(fail=True)
    out = run([ev(20, 9, "A", "Nowhere")], core=bad)
    assert "travel" not in out["days"][1]["events"][0] and out["travel"] == "unavailable"


def test_soon_events_get_a_live_answer():
    core = FakeCore()
    run([ev(19, 7, "Soon", "Near"), ev(19, 20, "Later", "Far")], core=core)
    live = {c[2]["destination"]: c[2]["realtime"] for c in core.calls}
    assert live == {"Near": True, "Far": False}


def test_all_day_multi_day_is_shown_once_and_symbol_is_off():
    events = [
        {"summary": "Trip", "start": "2026-11-18", "end": "2026-11-22", "all_day": True, "feed_colour": "#111", "feed_symbol": "🏡"},
        ev(19, 9, "Visit"),
    ]
    out = run(events)
    d0, d1 = out["days"][0], out["days"][1]
    assert d0["all_day"][0]["title"] == "Trip" and d0["all_day"][0]["through"] == "2026-11-21"
    assert d0["all_day"][0]["through_weekday"] == 5 and d1["all_day"] == []
    assert d0["events"][0]["title"] == "Visit"
    assert run(events, show_symbol=True)["days"][0]["events"][0]["title"] == "🏡 Visit"


def test_events_sorted_and_days_counted():
    out = run([ev(20, 17, "Late"), ev(20, 8, "Early")], days=3, show_travel="false")
    assert len(out["days"]) == 3 and out["travel"] == "off"
    assert [e["title"] for e in out["days"][1]["events"]] == ["Early", "Late"]
    assert out["days"][0]["is_today"] and out["days"][1]["date"] == "2026-11-20"


def test_no_calendar_core_and_leave_rounding():
    assert "error" in S._fetch(TZ, {}, ctx={}, now=NOW, cal=object())
    s = datetime(2026, 11, 20, 9, 0, tzinfo=AMS)
    assert S.leave_at(s, 22.1, 5) == s - timedelta(minutes=28)
    assert S._minutes({"service_response": {"routes": []}}) is None
