"""home_batteries: offline, with a fake Home Assistant Core. Every entity
here is made up (prefix ``inv``, car ``sensor.example_car_*``)."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("home_batteries_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]
D = S.D
AMS = ZoneInfo("Europe/Amsterdam")


def st(eid, state, **attrs):
    return {"entity_id": eid, "state": str(state), "attributes": attrs}


PROGRAMS = [("01:00", 5, "Grid"), ("10:30", 100, "Grid"), ("14:30", 5, "Disabled"), ("16:30", 5, "Disabled"), ("17:45", 5, "Disabled"), ("20:30", 5, "Disabled")]
STATES = [
    st("sensor.inv_battery", 53, unit_of_measurement="%"),
    st("sensor.inv_battery_state", "discharging"),
    st("sensor.inv_battery_power", 1226),
    st("select.inv_work_mode", "Zero Export To CT", options=["Export First", "Zero Export To Load", "Zero Export To CT"], friendly_name="Inv Work Mode"),
    st("select.inv_time_of_use", "Week"),
    st("sensor.example_car_soc", 86, unit_of_measurement="%"),
    st("sensor.example_car_target", 80, unit_of_measurement="%"),
    st("sensor.example_car_range", 358000, unit_of_measurement="m"),
    st("binary_sensor.example_car_charging", "off"),
    st("binary_sensor.example_car_plug", "on"),
]
for n, (t, soc, ch) in enumerate(PROGRAMS, 1):
    STATES += [st(f"time.inv_program_{n}_time", f"{t}:00"), st(f"number.inv_program_{n}_soc", soc), st(f"select.inv_program_{n}_charging", ch)]


class FakeCore:
    def is_configured(self):
        return True

    def get_states(self):
        return STATES

    def entity_choices(self, domains=None):
        return [{"value": s["entity_id"], "label": s["entity_id"]} for s in STATES if s["entity_id"].split(".")[0] in (domains or ())]


OPTS = {
    "home_device": "inv",
    "car_soc": "sensor.example_car_soc", "car_target": "sensor.example_car_target", "car_range": "sensor.example_car_range",
    "car_charging": "binary_sensor.example_car_charging", "car_plug": "binary_sensor.example_car_plug",
    "timezone": "Europe/Amsterdam",
}


def at(hh, mm=0):
    return datetime(2026, 11, 2, hh, mm, tzinfo=AMS)


def test_tiles() -> None:
    d = S.fetch(OPTS, {}, ctx={}, now=at(18, 40), core=FakeCore())
    home, car = d["tiles"]
    assert home == {"kind": "home", "name": "", "soc": 53, "target": 5, "state": "discharging", "mode": "zero_ct"}
    assert car == {"kind": "car", "name": "", "soc": 86, "target": 80, "km": 358, "charging": False, "plugged": True}


def test_current_slot_and_grid_threshold() -> None:
    states = {s["entity_id"]: s for s in STATES}
    b = D.read(states, "inv", at(11, 15), 10)
    assert b["current"]["start"] == 10 * 60 + 30 and b["current"]["target"] == 100 and b["current"]["grid"]
    assert b["next"]["start"] == 14 * 60 + 30
    assert not b["slots"][0]["grid"]  # "Grid" to 5% charges nothing
    assert D.read(states, "inv", at(0, 30), 10)["current"]["start"] == 20 * 60 + 30  # after midnight: the evening slot
    assert b["slots"][-1]["end"] == 60  # 20:30 runs to 01:00
    assert D.read(states, "inv", at(11, 15), 0)["slots"][0]["grid"]


def test_state_from_power_when_no_state_sensor() -> None:
    states = {s["entity_id"]: s for s in STATES if s["entity_id"] != "sensor.inv_battery_state"}
    assert D.read(states, "inv", at(9), 10)["state"] == "discharging"
    states["sensor.inv_battery_power"] = st("sensor.inv_battery_power", -900)
    assert D.read(states, "inv", at(9), 10)["state"] == "charging"


def test_range_units() -> None:
    assert S.km_of(st("x", 358000, unit_of_measurement="m")) == 358
    assert S.km_of(st("x", 220, unit_of_measurement="mi")) == 354
    assert S.km_of(st("x", 300, unit_of_measurement="km")) == 300


def test_device_choices() -> None:
    got = D.device_choices(STATES)
    assert got == [{"value": "inv", "label": "Inv (inv)"}]


def test_language_switch() -> None:
    d = S.fetch({**OPTS, "language": "nl"}, {}, ctx={}, now=at(18, 40), core=FakeCore())
    assert d["lang"] == "nl" and d["strings"]["home_battery"] == "Thuisbatterij"
    assert "strings" not in S.fetch(OPTS, {}, ctx={}, now=at(18, 40), core=FakeCore())


def test_empty_and_no_core() -> None:
    assert S.fetch({}, {}, ctx={}, core=FakeCore())["state"] == "empty"
    assert "error" in S.fetch(OPTS, {}, ctx={}, core=None) or S._core() is None


def test_entities_are_secrets() -> None:
    manifest = json.loads((HERE / "plugin.json").read_text())
    for o in manifest["cell_options"]:
        if o["name"].startswith(("home_device", "home_name", "car_")):
            assert o.get("secret") is True and o.get("mask") is False, o["name"]
