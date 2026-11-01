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
