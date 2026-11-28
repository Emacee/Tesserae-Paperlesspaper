"""energy_dynamic_price: the car's state of charge over the prices, offline with a fake Home Assistant Core."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("energy_dynamic_price_server_car", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]
AMS = ZoneInfo("Europe/Amsterdam")
T0 = datetime(2026, 11, 28, 0, 0, tzinfo=AMS)


def at(hours: float) -> str:
    return (T0 + timedelta(hours=hours)).astimezone(timezone.utc).isoformat()


class FakeCore:
    def __init__(self, soc_now="59", charging_now=False):
        self.soc_now, self.charging_now, self.asked = soc_now, charging_now, []

    def get_state(self, eid):
        return {"state": self.soc_now}

    def history(self, eid, *, hours=24, timeout=12):
        self.asked.append(eid)
        if eid == "sensor.car_soc":
            return [
                {"state": "38", "last_changed": at(0)}, {"state": "unavailable", "last_changed": at(1)},
                {"state": "60", "last_changed": at(2.5)}, {"state": "80", "last_changed": at(4.5)},
                {"state": "70", "last_changed": at(9)}, {"state": "59", "last_changed": at(16)},
            ]
        if eid == "binary_sensor.car_charging":
            rows = [{"state": "off", "last_changed": at(0)}, {"state": "on", "last_changed": at(0.5)}, {"state": "off", "last_changed": at(4.5)}]
            if self.charging_now:
                rows.append({"state": "on", "last_changed": at(17)})
            return rows
        return []


def view():
    return {"start": T0.isoformat(), "minutes": 15, "slots": [{"t": "", "p": 1}] * 192}


NOW = T0 + timedelta(hours=17.5)


def test_the_state_of_charge_is_a_line_and_charging_stretches_are_listed() -> None:
    out = S.car_overlay(view(), {"car_soc": "sensor.car_soc", "car_charging": "binary_sensor.car_charging", "car_name": "ID.7"}, NOW, core=FakeCore())
    assert out["soc"] == 59 and out["name"] == "ID.7" and abs(out["now_x"] - 70.0) < 0.01
    hist = out["history"]
    assert hist[0] == [0.0, 38.0] and hist[-1] == [out["now_x"], 59.0]
    assert all(v != "unavailable" for _, v in hist)  # a sample that is not a number is dropped
    assert out["charging"] == [[2.0, 18.0]]  # 00:30 to 04:30


def test_a_car_that_is_charging_now_runs_to_now() -> None:
    out = S.car_overlay(view(), {"car_soc": "sensor.car_soc", "car_charging": "binary_sensor.car_charging"}, NOW, core=FakeCore(charging_now=True))
    assert out["charging"][-1] == [68.0, out["now_x"]]


def test_without_a_charging_sensor_or_a_value_now() -> None:
    core = FakeCore(soc_now="unavailable")
    out = S.car_overlay(view(), {"car_soc": "sensor.car_soc"}, NOW, core=core)
    assert out["charging"] == [] and out["soc"] == 59  # the last known value
    assert core.asked == ["sensor.car_soc"]
    assert S.car_overlay(view(), {}, NOW, core=FakeCore())["reason"] == "no car sensor"


def test_the_car_sensors_are_secrets_and_a_choice_of_entities() -> None:
    import json

    opts = {o["name"]: o for o in json.loads((HERE / "plugin.json").read_text())["cell_options"]}
    for name in ("car_soc", "car_charging", "car_name"):
        assert opts[name]["secret"] is True
    assert opts["car_soc"]["choices_from"] == "entity"


def test_a_value_from_before_midnight_is_carried_to_the_start() -> None:
    class Idle(FakeCore):
        def history(self, eid, *, hours=24, timeout=12):
            return [{"state": "57", "last_changed": at(-20)}]

    out = S.car_overlay(view(), {"car_soc": "sensor.car_soc"}, NOW, core=Idle(soc_now="57"))
    assert out["history"][0] == [0.0, 57.0] and out["history"][-1] == [out["now_x"], 57.0]
