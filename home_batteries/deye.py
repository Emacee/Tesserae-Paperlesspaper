"""A Deye hybrid inverter as the Solarman integration (ha-solarman) names it
in Home Assistant, read from one device prefix: the ``inverter`` in
``select.inverter_work_mode``. Shared by Home batteries and Energy, Dynamic
Price (which loads this file by path).

Entities read, for prefix ``p``:

- ``sensor.p_battery``: state of charge, %
- ``sensor.p_battery_state``: charging / idle / discharging (else the sign of
  ``sensor.p_battery_power``, positive while discharging)
- ``select.p_work_mode``: Export First / Zero Export To Load / Zero Export To CT
- ``select.p_time_of_use``: the time-of-use program on or off
- ``time.p_program_N_time``, ``number.p_program_N_soc``,
  ``select.p_program_N_charging`` for N = 1..6: the six time-of-use slots,
  each from its start to the next one's, with a target SOC and whether it
  may charge from the grid (or the generator)
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Any

SLOTS = 6
MODES = {
    "export first": "export_first",
    "zero export to load": "zero_load",
    "zero export to ct": "zero_ct",
}


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _minutes(hhmm: Any) -> int | None:
    text = str(hhmm or "")
    with contextlib.suppress(ValueError, IndexError):
        h, m = text.split(":")[:2]
        return int(h) * 60 + int(m)
    return None


def device_choices(states: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Every device with a work-mode select that offers the Deye modes."""
    out = []
    for st in states:
        eid = str(st.get("entity_id") or "")
        if not (eid.startswith("select.") and eid.endswith("_work_mode")):
            continue
        opts = [str(o).lower() for o in (st.get("attributes") or {}).get("options") or []]
        if not any(o in MODES for o in opts):
            continue
        prefix = eid[len("select."):-len("_work_mode")]
        name = str((st.get("attributes") or {}).get("friendly_name") or prefix)
        name = name[: -len(" Work Mode")] if name.lower().endswith(" work mode") else name
        out.append({"value": prefix, "label": f"{name} ({prefix})"})
    return sorted(out, key=lambda c: c["label"].lower())


def entity_ids(prefix: str) -> list[str]:
    ids = [f"sensor.{prefix}_battery", f"sensor.{prefix}_battery_state", f"sensor.{prefix}_battery_power",
           f"select.{prefix}_work_mode", f"select.{prefix}_time_of_use"]
    for n in range(1, SLOTS + 1):
        ids += [f"time.{prefix}_program_{n}_time", f"number.{prefix}_program_{n}_soc", f"select.{prefix}_program_{n}_charging"]
    return ids


def read(states: dict[str, dict[str, Any]], prefix: str, now: datetime, grid_min_soc: float = 10) -> dict[str, Any]:
    """The battery now and its schedule, from a {entity_id: state} map."""
    s = lambda kind, name: (states.get(f"{kind}.{prefix}_{name}") or {}).get("state")  # noqa: E731
    soc = _num(s("sensor", "battery"))
    state = str(s("sensor", "battery_state") or "").lower()
    if state not in ("charging", "idle", "discharging"):
        p = _num(s("sensor", "battery_power"))
        state = "" if p is None else "discharging" if p > 50 else "charging" if p < -50 else "idle"
    mode = MODES.get(str(s("select", "work_mode") or "").lower(), "")
    tou = str(s("select", "time_of_use") or "").lower()
    slots = []
    if tou not in ("disabled", "off"):
        for n in range(1, SLOTS + 1):
            start = _minutes(s("time", f"program_{n}_time"))
            target = _num(s("number", f"program_{n}_soc"))
            charging = str(s("select", f"program_{n}_charging") or "").lower()
            if start is None or target is None:
                continue
            slots.append({"n": n, "start": start, "target": round(target),
                          "grid": charging not in ("", "disabled", "none", "off") and target > grid_min_soc})
        slots.sort(key=lambda x: x["start"])
        for i, sl in enumerate(slots):
            sl["end"] = slots[(i + 1) % len(slots)]["start"]
    current = None
    if slots:
        m = now.hour * 60 + now.minute
        current = max((x for x in slots if x["start"] <= m), key=lambda x: x["start"], default=slots[-1])
    nxt = slots[(slots.index(current) + 1) % len(slots)] if current else None
    return {
        "soc": round(soc) if soc is not None else None,
        "state": state,
        "mode": mode,
        "slots": slots,
        "current": current,
        "next": nxt,
    }


def hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"
