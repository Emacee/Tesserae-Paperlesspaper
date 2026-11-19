"""agenda_list: offline, with fake Calendar Core and Home Assistant Core.
The events, places and drive times here are made up."""

from __future__ import annotations

import importlib.util
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agenda_list_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]

AMS = ZoneInfo("Europe/Amsterdam")
REAL_GET_JSON = S._get_json  # before the offline stub replaces it
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

    def get_state(self, eid):
        if eid == "zone.home":
            return {"attributes": {"latitude": 52.27, "longitude": 4.97}}
        raise KeyError(eid)

    def call_service_with_response(self, domain, service, *, data=None, timeout=10):
        self.calls.append((domain, service, data))
        if self.fail:
            raise RuntimeError("no route")
        return {"service_response": {"routes": [{"duration": self.minutes + 9}, {"duration": self.minutes}]}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No network: OpenStreetMap and OSRM answer from this table unless a test
    sets its own. Module state is cleared between tests."""
    S._cache.clear(), S._geo.clear(), S._geo_t.clear(), S._geo_loaded.clear()
    S._waze_down[0] = 0.0
    S._last_geo[0] = 0.0
    del S._trace[:]
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    calls = []

    def get_json(url):
        calls.append(url)
        if "nominatim" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
            places = {"Vinkeveen": ("52.21", "4.93"), "Amsterdam": ("52.37", "4.90")}
            return [{"lat": places[q][0], "lon": places[q][1]}] if q in places else []
        if "osrm" in url:
            return {"routes": [{"duration": 1200.0}]}  # 20 minutes
        return None

    monkeypatch.setattr(S, "_get_json", get_json)
    return calls


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
    assert e["travel"] == {"min": 35, "leave": "18:20", "est": False}  # 19:00 - 35 - 5
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
    out = run([ev(20, 9, "A", "Nowhere")], core=bad, travel_source="waze")
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


def test_osrm_when_waze_does_not_answer():
    out = run([ev(20, 10, "Visit", "Vinkeveen")], core=FakeCore(fail=True))
    e = out["days"][1]["events"][0]
    # 20 min + 15% surcharge = 23 min; 10:00 - 23 - 5 = 09:32
    assert e["travel"] == {"min": 23, "leave": "09:32", "est": True}
    assert out["travel"] == "ok" and out["via"] == "osrm"


def test_waze_wins_when_it_answers_and_is_not_an_estimate():
    out = run([ev(20, 10, "Visit", "Vinkeveen")], core=FakeCore(minutes=30))
    assert out["days"][1]["events"][0]["travel"]["est"] is False and out["via"] == "waze"


def test_osrm_only_never_asks_waze_and_surcharge_is_an_option():
    core = FakeCore()
    out = run([ev(20, 10, "Visit", "Vinkeveen")], core=core, travel_source="osrm", osrm_extra_pct=0)
    assert core.calls == [] and out["days"][1]["events"][0]["travel"]["min"] == 20


def test_unknown_place_shows_no_drive_and_waze_is_skipped_for_a_while():
    core = FakeCore(fail=True)
    out = run([ev(20, 10, "Visit", "Nowhere at all")], core=core)
    assert out["travel"] == "unavailable" and "travel" not in out["days"][1]["events"][0]
    out = run([ev(20, 10, "Visit", "Vinkeveen")], core=core)  # run() clears the cache, not the breaker
    assert len(core.calls) == 1  # the second run went straight to OSRM


def test_places_are_geocoded_once_kept_on_disk_and_budgeted(offline, tmp_path):
    S._cache.clear()
    events = [ev(20, 10, "A", "Vinkeveen"), ev(21, 10, "B", "Vinkeveen")]
    S._fetch(TZ, {}, ctx={"data_dir": str(tmp_path)}, now=NOW, cal=FakeCal(events), core=FakeCore(fail=True))
    assert sum("nominatim" in u for u in offline) == 1  # home is a zone (no lookup); the place once, not per event
    assert (tmp_path / "geocode.json").exists()
    S._geo.clear(), S._geo_loaded.clear(), S._cache.clear()
    offline.clear()
    S._fetch(TZ, {}, ctx={"data_dir": str(tmp_path)}, now=NOW, cal=FakeCal(events), core=FakeCore(fail=True))
    assert not any("nominatim" in u for u in offline)  # read back from disk
    many = [ev(20, 8 + i, f"E{i}", f"Place {i}") for i in range(8)]
    S._cache.clear(), S._geo.clear(), S._geo_t.clear()
    offline.clear()
    run(many, core=FakeCore(fail=True))
    assert sum("nominatim" in u for u in offline) <= S.GEOCODE_PER_FETCH


def test_origin_can_be_coordinates_or_a_zone():
    assert S.home_position("52.1, 5.2", None, [4], None) == (52.1, 5.2)
    assert S.home_position("zone.home", FakeCore(), [4], None) == (52.27, 4.97)
    assert S.home_position("zone.nope", FakeCore(), [4], None) is None


def test_multi_line_locations_become_one_line():
    out = run([ev(20, 10, "Dinner", "Omakase Amsterdam\nFerdinand Bolstraat 11H\n1072 LK")], core=FakeCore(), travel_source="osrm")
    assert out["days"][1]["events"][0]["location"] == "Omakase Amsterdam, Ferdinand Bolstraat 11H, 1072 LK"


def test_get_json_prefers_tesserae_fetch_and_keeps_the_reason(monkeypatch):
    import sys
    import types

    mod = types.ModuleType("app.net_guard")
    seen = {}

    def fetch_json(url, headers=None, timeout=0):
        seen["headers"] = headers
        if "bad" in url:
            raise OSError("blocked by test")
        return {"ok": True}

    mod.fetch_json = fetch_json
    monkeypatch.setitem(sys.modules, "app", types.ModuleType("app"))
    monkeypatch.setitem(sys.modules, "app.net_guard", mod)
    assert REAL_GET_JSON("https://example.org/good") == {"ok": True}
    assert seen["headers"]["User-Agent"] == S.USER_AGENT
    assert REAL_GET_JSON("https://example.org/bad") is None
    assert "blocked by test" in S._last_error[0]


def test_the_note_says_why_when_nothing_is_found():
    out = run([ev(20, 10, "Visit", "Nowhere at all")], core=FakeCore(fail=True))
    assert out["travel"] == "unavailable"
    assert "Waze: RuntimeError" in out["why"] and "place not found: Nowhere at all" in out["why"]
    S._cache.clear()
    out = S._fetch(TZ, {}, ctx={}, now=NOW, cal=FakeCal([ev(20, 10, "Visit", "Vinkeveen")]), core=None)
    assert "home zone.home" in out["why"] and "NoneType" in out["why"]


def test_core_is_called_with_the_flask_app_context_in_worker_threads():
    flask = pytest.importorskip("flask")

    class NeedsContext(FakeCore):
        def call_service_with_response(self, domain, service, *, data=None, timeout=10):
            flask.current_app.name  # raises outside an application context, like Home Assistant Core's settings
            return super().call_service_with_response(domain, service, data=data, timeout=timeout)

    with flask.Flask("test").app_context():
        out = run([ev(20, 10, "Visit", "Cafe")], core=NeedsContext(minutes=10), travel_source="waze")
    assert out["days"][1]["events"][0]["travel"]["min"] == 10, out["why"]


def test_a_venue_name_in_front_of_an_address_is_dropped_when_not_found(offline):
    assert S._candidates("Omakase Amsterdam\nFerdinand".replace("\n", ", ")) == ["Omakase Amsterdam, Ferdinand"]
    full = "Omakase Amsterdam, Ferdinand Bolstraat 11H, 1072 LK"
    assert S._candidates(full) == [full, "Ferdinand Bolstraat 11H, 1072 LK"]
    got = S.geocode(full, None, [4])
    assert got is None  # neither form is in the offline table
    assert sum("nominatim" in u for u in offline) == 2
