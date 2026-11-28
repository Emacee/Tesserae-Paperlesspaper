"""travel_time: offline, with a fake Home Assistant Core. The sensors and names
here are made up."""

from __future__ import annotations

import importlib.util
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("travel_time_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]

AMS = ZoneInfo("Europe/Amsterdam")


class FakeCore:
    def __init__(self, states: dict[str, dict], history: dict[str, list] | None = None) -> None:
        self.states, self.hist, self.history_calls = states, history or {}, 0

    def is_configured(self) -> bool:
        return True

    def get_states(self) -> list[dict]:
        return list(self.states.values())

    def get_state(self, eid: str) -> dict:
        return self.states[eid]

    def friendly_name(self, st: dict) -> str:
        return st.get("attributes", {}).get("friendly_name") or st["entity_id"]

    def history(self, eid: str, *, hours: int = 24, timeout: int = 12) -> list[dict]:
        self.history_calls += 1
        return self.hist.get(eid, [])


def waze(eid: str, minutes: float, route: str = "A1 - E30; A10") -> dict:
    return {
        "entity_id": eid,
        "state": str(minutes),
        "attributes": {
            "friendly_name": eid.split(".")[1].replace("_", " "),
            "unit_of_measurement": "min",
            "device_class": "duration",
            "attribution": "Powered by Waze",
            "route": route,
            "distance": 31.4,
        },
    }


OPTS = {
    "person_1_name": "Alex",
    "person_1_to_work": "sensor.example_a_to_work",
    "person_1_to_home": "sensor.example_a_to_home",
    "person_2_name": "",
    "person_2_to_work": "sensor.example_b_to_work",
    "person_2_to_home": "sensor.example_b_to_home",
    "timezone": "Europe/Amsterdam",
}
STATES = {
    e: waze(e, m)
    for e, m in [
        ("sensor.example_a_to_work", 27.4),
        ("sensor.example_a_to_home", 35.2),
        ("sensor.example_b_to_work", 41.0),
        ("sensor.example_b_to_home", 25.1),
    ]
}
STATES["sensor.outside_temp"] = {"entity_id": "sensor.outside_temp", "state": "12", "attributes": {"unit_of_measurement": "°C"}}


def at(day: int, hh: int, mm: int = 0) -> datetime:
    # 2 Nov 2026 is a Monday
    return datetime(2026, 11, day, hh, mm, tzinfo=AMS)


def test_roads() -> None:
    assert S.roads("A2 - E35; A12 - E30 - E35") == ["A2", "A12"]
    assert S.roads("A2 - Parallel") == ["A2"]
    assert S.roads("E19") == ["E19"]
    assert S.roads("") == []


def test_choices_lists_travel_sensors_waze_first(monkeypatch) -> None:
    states = dict(STATES)
    states["sensor.gmaps_x"] = {"entity_id": "sensor.gmaps_x", "state": "30", "attributes": {"unit_of_measurement": "min", "friendly_name": "A gmaps"}}
    monkeypatch.setattr(S, "_core", lambda: FakeCore(states))
    got = S.choices("travel_sensor")
    values = [c["value"] for c in got]
    assert values[0] == ""
    assert "sensor.outside_temp" not in values
    assert values[-1] == "sensor.gmaps_x"  # not Waze: after the Waze ones
    assert "· 27 min" in got[values.index("sensor.example_a_to_work")]["label"]
    assert S.choices("other") == []


def test_morning_is_to_work_afternoon_is_home(tmp_path: Path) -> None:
    core = FakeCore(STATES)
    am = S.fetch(OPTS, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 7, 45), core=core)
    assert am["direction"] == "work"
    assert [p["min"] for p in am["people"]] == [27, 41]
    assert am["people"][0]["name"] == "Alex" and am["people"][0]["initial"] == "A"
    assert am["people"][1]["name"] == "example b to work"  # blank name: the sensor's
    assert am["people"][0]["roads"] == ["A1", "A10"]
    assert am["source"] == "Waze"
    pm = S.fetch(OPTS, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 14, 0), core=core)
    assert pm["direction"] == "home"
    assert [p["min"] for p in pm["people"]] == [35, 25]
    early = S.fetch({**OPTS, "switch_hour": "16"}, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 15, 0), core=core)
    assert early["direction"] == "work"


def test_weekend_hidden_unless_shown(tmp_path: Path) -> None:
    core = FakeCore(STATES)
    sat = S.fetch(OPTS, {}, ctx={"data_dir": str(tmp_path)}, now=at(7, 9), core=core)
    assert sat["state"] == "off"
    shown = S.fetch({**OPTS, "weekend": "show"}, {}, ctx={"data_dir": str(tmp_path)}, now=at(7, 9), core=core)
    assert shown["state"] == "ok"


def test_no_sensors_is_empty(tmp_path: Path) -> None:
    got = S.fetch({"timezone": "Europe/Amsterdam"}, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 9), core=FakeCore(STATES))
    assert got["state"] == "empty"


def test_no_core() -> None:
    got = S.fetch(OPTS, {}, ctx={"data_dir": "."}, now=at(2, 9), core=None)
    assert "error" in got


def _history(eid: str, weekday_minutes: float, other: float, weeks: int = 4) -> list[dict]:
    """A sample every 15 minutes over ``weeks`` weeks: Mondays 17:00-18:00 at
    ``weekday_minutes``, everything else at ``other``."""
    out = []
    t = at(2, 0) - timedelta(weeks=weeks)
    end = at(2, 0)
    while t < end:
        v = weekday_minutes if (t.weekday() == 0 and 17 <= t.hour < 18) else other
        out.append({"state": str(v), "last_changed": t.astimezone(timezone.utc).isoformat()})
        t += timedelta(minutes=15)
    return out


def test_baseline_table_and_normal() -> None:
    samples = _history("x", 40, 25)
    table = S.build_baseline(samples, AMS, at(2, 0))
    counts = S._count(samples, AMS)
    assert S.normal_at(table, counts, at(9, 17, 20)) == 40  # a Monday, 17:20
    assert S.normal_at(table, counts, at(10, 17, 20)) == 25  # a Tuesday
    assert S.normal_at({}, {}, at(9, 17)) is None


def test_baseline_value_held_until_next_change() -> None:
    # written only when it changes: 30 at 08:00, 50 at 09:00 on one Monday
    samples = [
        {"state": "30", "last_changed": at(2, 8).astimezone(timezone.utc).isoformat()},
        {"state": "50", "last_changed": at(2, 9).astimezone(timezone.utc).isoformat()},
    ]
    table = S.build_baseline(samples, AMS, at(2, 10))
    assert table[f"0-{(8 * 60 + 30) // 15}"] == 30
    assert table[f"0-{(9 * 60 + 30) // 15}"] == 50
    # never held for more than two hours
    assert f"0-{(10 * 60 + 30) // 15}" not in S.build_baseline(samples[:1], AMS, at(2, 12))


def test_delay_against_normal(tmp_path: Path) -> None:
    states = dict(STATES)
    states["sensor.example_a_to_home"] = waze("sensor.example_a_to_home", 48)  # normal 40: +8
    states["sensor.example_b_to_home"] = waze("sensor.example_b_to_home", 26)  # normal 25: +1, under the threshold
    core = FakeCore(states, {
        "sensor.example_a_to_home": _history("a", 40, 25),
        "sensor.example_b_to_home": _history("b", 25, 25),
    })
    ctx = {"data_dir": str(tmp_path)}
    S.fetch(OPTS, {}, ctx=ctx, now=at(9, 17, 20), core=core)  # starts the baseline threads
    deadline = time.time() + 5
    while S._building and time.time() < deadline:
        time.sleep(0.05)
    got = S.fetch(OPTS, {}, ctx=ctx, now=at(9, 17, 20), core=core)
    a, b = got["people"]
    assert (a["min"], a["normal"], a["late"]) == (48, 40, 8)
    assert (b["min"], b["normal"], b["late"]) == (26, 25, 0)
    # the table is kept: no new history call within the day
    calls = core.history_calls
    S.fetch(OPTS, {}, ctx=ctx, now=at(9, 17, 25), core=core)
    assert core.history_calls == calls
    files = list((tmp_path / "baseline").glob("*.json"))
    assert files and all("example" not in f.name for f in files)  # the file names do not carry the sensor
    assert json.loads(files[0].read_text())["weeks"] == 6


def test_sensors_and_names_are_secrets() -> None:
    manifest = json.loads((HERE / "plugin.json").read_text())
    people = [o for o in manifest["cell_options"] if o["name"].startswith("person_")]
    assert people and all(o.get("secret") is True and o.get("mask") is False for o in people)


def test_language_switch(tmp_path: Path) -> None:
    got = S.fetch({**OPTS, "language": "de"}, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 7, 45), core=FakeCore(STATES))
    assert got["lang"] == "de" and got["strings"]["to_work"] == "Fahrzeit zur Arbeit"


# ----------------------------------------------------------------------
# OSRM, when a sensor has no value
# ----------------------------------------------------------------------
import pytest  # noqa: E402


@pytest.fixture
def osrm(monkeypatch):
    """No network: OpenStreetMap and OSRM answer from here. Returns the URLs asked."""
    S._geo.clear(), S._geo_miss.clear(), S._geo_loaded.clear(), S._route_cache.clear()
    S._last_geo[0] = 0.0
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    asked: list[str] = []

    def get_json(url):
        asked.append(url)
        if "nominatim" in url:
            q = S.urllib.parse.parse_qs(S.urllib.parse.urlparse(url).query)["q"][0]
            places = {"Euclideslaan 251, Utrecht": ("52.09", "5.17")}
            return [{"lat": places[q][0], "lon": places[q][1]}] if q in places else []
        if "osrm" in url:
            return {"routes": [{"duration": 1200.0}]}  # 20 minutes
        return None

    monkeypatch.setattr(S, "_get_json", get_json)
    return asked


def down_states():
    states = dict(STATES)
    states["sensor.example_a_to_work"] = {"entity_id": "sensor.example_a_to_work", "state": "unavailable", "attributes": {"friendly_name": "a"}}
    states["sensor.example_a_to_home"] = {"entity_id": "sensor.example_a_to_home", "state": "unavailable", "attributes": {"friendly_name": "a"}}
    states["zone.home"] = {"entity_id": "zone.home", "state": "0", "attributes": {"latitude": 52.27, "longitude": 4.97}}
    return states


def test_osrm_fills_in_when_the_sensor_has_no_value(osrm, tmp_path) -> None:
    opts = {**OPTS, "person_1_work": "Euclideslaan 251, Utrecht"}
    out = S._fetch(opts, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 8), core=FakeCore(down_states()))
    a, b = out["people"]
    assert a["min"] == 23 and a["est"] is True and "normal" not in a and "late" not in a  # 20 min + 15%
    assert b["min"] == 41 and "est" not in b  # a sensor with a value is used as it is
    assert out["source"] == "Waze" and out["est"] is True
    assert (tmp_path / "geocode.json").exists()


def test_osrm_direction_and_only_when_allowed(osrm, tmp_path) -> None:
    opts = {**OPTS, "person_1_work": "Euclideslaan 251, Utrecht"}
    out = S._fetch(opts, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 16), core=FakeCore(down_states()))  # after 14:00: home
    assert out["direction"] == "home" and out["people"][0]["est"] is True
    route = [u for u in osrm if "osrm" in u][0]
    assert route.split("/driving/")[1].startswith("5.17,52.09;4.97,52.27")  # work first, then home
    osrm.clear()
    out = S._fetch({**opts, "travel_source": "waze"}, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 8), core=FakeCore(down_states()))
    assert out["people"][0]["min"] is None and not osrm


def test_a_person_with_only_a_work_address_is_shown_and_places_are_not_looked_up_twice(osrm, tmp_path) -> None:
    opts = {"timezone": "Europe/Amsterdam", "person_1_name": "Sam", "person_1_work": "Euclideslaan 251, Utrecht"}
    core = FakeCore(down_states())
    for _ in range(2):
        out = S._fetch(opts, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 8), core=core)
    assert out["state"] == "ok" and out["people"][0]["name"] == "Sam" and out["people"][0]["min"] == 23
    assert sum("nominatim" in u for u in osrm) == 1 and sum("osrm" in u for u in osrm) == 1


def test_an_address_that_is_not_found_gives_no_value(osrm, tmp_path) -> None:
    opts = {**OPTS, "person_1_work": "Nowhere 1"}
    out = S._fetch(opts, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 8), core=FakeCore(down_states()))
    assert out["people"][0]["min"] is None and "est" not in out["people"][0] and out["est"] is False


# ----------------------------------------------------------------------
# The car beside the commutes, and the strip
# ----------------------------------------------------------------------
CAR_STATES = {
    "sensor.car_range": {"entity_id": "sensor.car_range", "state": "172", "attributes": {"unit_of_measurement": "mi"}},
    "binary_sensor.car_plug": {"entity_id": "binary_sensor.car_plug", "state": "off", "attributes": {}},
    "binary_sensor.car_charging": {"entity_id": "binary_sensor.car_charging", "state": "unavailable", "attributes": {}},
}


def test_the_car_block_reads_range_in_km_and_plug_state(tmp_path: Path) -> None:
    opts = {**OPTS, "layout": "strip", "car_range": "sensor.car_range", "car_plug": "binary_sensor.car_plug", "car_charging": "binary_sensor.car_charging", "car_name": "ID.7"}
    out = S._fetch(opts, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 8), core=FakeCore({**STATES, **CAR_STATES}))
    assert out["layout"] == "strip" and out["car"] == {"name": "ID.7", "km": 277, "plugged": False, "charging": None, "soc": None}
    assert [p["name"] for p in out["people"]][0] == "Alex" and out["state"] == "ok"


def test_without_car_sensors_there_is_no_car(tmp_path: Path) -> None:
    out = S._fetch(OPTS, {}, ctx={"data_dir": str(tmp_path)}, now=at(2, 8), core=FakeCore(STATES))
    assert out["car"] is None and out["layout"] == "rows"


def test_at_the_weekend_a_strip_keeps_the_car_but_rows_stay_empty(tmp_path: Path) -> None:
    car = {"car_range": "sensor.car_range"}
    core = FakeCore({**STATES, **CAR_STATES})
    saturday = at(7, 9)
    strip = S._fetch({**OPTS, **car, "layout": "strip"}, {}, ctx={"data_dir": str(tmp_path)}, now=saturday, core=core)
    assert strip["state"] == "ok" and strip["people"] == [] and strip["car"]["km"] == 277
    rows = S._fetch({**OPTS, **car}, {}, ctx={"data_dir": str(tmp_path)}, now=saturday, core=core)
    assert rows["state"] == "off"


def test_the_car_sensors_are_secrets_and_a_choice_of_entities() -> None:
    manifest = json.loads((HERE / "plugin.json").read_text())
    opts = {o["name"]: o for o in manifest["cell_options"]}
    for name in ("car_range", "car_plug", "car_charging", "car_name"):
        assert opts[name]["secret"] is True
    assert opts["car_range"]["choices_from"] == "entity" and opts["layout"]["default"] == "rows"
