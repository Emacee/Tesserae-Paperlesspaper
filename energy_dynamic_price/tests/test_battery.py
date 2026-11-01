"""energy_dynamic_price: the home battery over the prices, offline with a
fake Home Assistant Core. The device prefix ``inv`` is made up."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("energy_dynamic_price_server_b", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]
AMS = ZoneInfo("Europe/Amsterdam")


def st(eid, state, **attrs):
    return {"entity_id": eid, "state": str(state), "attributes": attrs}


PROGRAMS = [("01:00", 5, "Grid"), ("10:30", 100, "Grid"), ("14:30", 5, "Disabled"), ("16:30", 5, "Disabled"), ("17:45", 5, "Disabled"), ("20:30", 5, "Disabled")]
STATES = [st("sensor.inv_battery", 53), st("sensor.inv_battery_state", "discharging"), st("select.inv_work_mode", "Zero Export To CT", options=["Export First", "Zero Export To CT"]), st("select.inv_time_of_use", "Week")]
for n, (t, soc, ch) in enumerate(PROGRAMS, 1):
    STATES += [st(f"time.inv_program_{n}_time", f"{t}:00"), st(f"number.inv_program_{n}_soc", soc), st(f"select.inv_program_{n}_charging", ch)]


class FakeCore:
    def get_states(self):
        return STATES

    def history(self, eid, *, hours=24, timeout=12):
        assert eid == "sensor.inv_battery"
        t0 = datetime(2026, 11, 2, 0, 0, tzinfo=AMS)
        return [{"state": str(60 - k), "last_changed": (t0 + timedelta(minutes=10 * k)).astimezone(timezone.utc).isoformat()} for k in range(0, 112)]


def view(now):
    start = datetime(2026, 11, 2, 0, 0, tzinfo=AMS)
    return {"start": start.isoformat(), "minutes": 15, "slots": [{"t": "", "p": 1}] * 192}


def test_overlay() -> None:
    now = datetime(2026, 11, 2, 18, 40, tzinfo=AMS)
    b = S.battery_overlay(view(now), {"battery_device": "inv"}, now, core=FakeCore())
    assert b["soc"] == 53
    assert abs(b["now_x"] - (18 * 4 + 40 / 15)) < 0.01
    # the 20:30 slot of the night before runs to 01:00: the window starts inside it
    assert b["segments"][0] == {"x0": 0.0, "x1": 4.0, "target": 5, "grid": False, "n": 6}
    grid = [g for g in b["segments"] if g["grid"]]
    assert [(g["x0"], g["x1"]) for g in grid] == [(42.0, 58.0), (138.0, 154.0)]  # 10:30-14:30, today and tomorrow
    assert b["current"]["x0"] == 71.0 and b["current"]["x1"] == 82.0  # 17:45-20:30
    assert b["slot"] == {"from": "17:45", "till": "20:30", "target": 5, "grid": False}
    assert b["next"] == {"from": "20:30", "target": 5}
    hist = b["history"]
    assert hist[0][0] == 0.0 and hist[-1] == [b["now_x"], 53.0]
    assert all(hist[i + 1][0] - hist[i][0] >= 0 for i in range(len(hist) - 1))


def test_no_history_when_off() -> None:
    now = datetime(2026, 11, 2, 9, 0, tzinfo=AMS)
    b = S.battery_overlay(view(now), {"battery_device": "inv", "battery_history": False}, now, core=FakeCore())
    assert "history" not in b


def test_device_is_a_secret() -> None:
    manifest = json.loads((HERE / "plugin.json").read_text())
    o = next(o for o in manifest["cell_options"] if o["name"] == "battery_device")
    assert o["secret"] is True and o["mask"] is False


def test_language_switch() -> None:
    lang, strings = S.strings_for({"language": "nl"})
    assert lang == "nl" and strings["title_battery"] == "Stroomprijs & thuisbatterij"
    assert S.strings_for({"language": "auto"}) == ("", {})
