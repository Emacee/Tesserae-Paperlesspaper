"""home_batteries: small rings for the batteries in the house.

The home battery (a Deye inverter through the Solarman integration): its
state of charge, whether it is charging, discharging or resting, its work
mode, and the target of the time-of-use slot it is in. The car (any
integration; Tibber's for a Volkswagen, for example): its state of charge,
its charge limit, its range in km, and whether it is charging or plugged
in. Each is optional.

Everything the page reads is picked in the cell's options and kept there as
a secret: nothing about the house or the car is in this widget.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _deye() -> Any:
    name = "_tesserae_plugins.home_batteries.deye"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _HERE / "deye.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


D = _deye()


def _core() -> Any:
    with contextlib.suppress(Exception):
        from flask import current_app

        plugin = current_app.config["PLUGIN_REGISTRY"].get("ha_core")
        return plugin.server_module if plugin is not None else None
    return None


def choices(name: str) -> list[dict[str, str]]:
    core = _core()
    if core is None:
        return []
    if not core.is_configured():
        return [{"value": "", "label": "Set HA URL + token in Settings → Widgets → Home Assistant Core"}]
    try:
        states = core.get_states()
    except Exception:  # noqa: BLE001
        return [{"value": "", "label": "Home Assistant unreachable, check URL + token"}]
    if name == "solarman_device":
        return [{"value": "", "label": "—"}] + D.device_choices(states)
    if name == "entity":
        return [{"value": "", "label": "—"}] + core.entity_choices(("sensor", "binary_sensor"))
    return []


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def km_of(st: dict[str, Any]) -> int | None:
    """A range sensor in km, whatever unit it reports (m, km, mi)."""
    v = _num((st or {}).get("state"))
    if v is None:
        return None
    unit = str(((st or {}).get("attributes") or {}).get("unit_of_measurement") or "km").lower()
    factor = {"m": 0.001, "km": 1.0, "mi": 1.609344}.get(unit, 1.0)
    return round(v * factor)


def _on(st: dict[str, Any]) -> bool | None:
    s = str((st or {}).get("state") or "").lower()
    return True if s in ("on", "true", "charging", "plugged") else False if s in ("off", "false") else None


def _local(now: datetime | None, options: dict[str, Any]) -> datetime:
    tz = None
    with contextlib.suppress(Exception):
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(str(options.get("timezone"))) if options.get("timezone") else None
    now = now or datetime.now(timezone.utc)
    return now.astimezone(tz) if tz else now.astimezone()


def _fetch(
    options: dict[str, Any],
    settings: dict[str, Any],
    *,
    ctx: dict[str, Any],
    now: datetime | None = None,
    core: Any = None,
) -> dict[str, Any]:
    del settings, ctx
    core = core if core is not None else _core()
    if core is None:
        return {"error": "Install the Home Assistant Core plugin to use this widget."}
    local = _local(now, options)
    try:
        states = {str(s.get("entity_id")): s for s in core.get_states() if isinstance(s, dict)}
    except Exception as err:  # noqa: BLE001 - the cell says so
        return {"error": f"Home Assistant unreachable ({type(err).__name__})."}
    tiles: list[dict[str, Any]] = []
    prefix = str(options.get("home_device") or "").strip()
    if prefix:
        try:
            min_soc = float(options.get("grid_min_soc", 10))
        except (TypeError, ValueError):
            min_soc = 10.0
        b = D.read(states, prefix, local, min_soc)
        cur = b["current"]
        tiles.append({
            "kind": "home",
            "name": str(options.get("home_name") or "").strip(),
            "soc": b["soc"],
            "target": cur["target"] if cur else None,
            "state": b["state"],
            "mode": b["mode"],
        })
    soc_id = str(options.get("car_soc") or "").strip()
    if soc_id:
        g = lambda key: states.get(str(options.get(key) or "").strip()) or {}  # noqa: E731
        soc = _num(g("car_soc").get("state"))
        target = _num(g("car_target").get("state"))
        tiles.append({
            "kind": "car",
            "name": str(options.get("car_name") or "").strip(),
            "soc": round(soc) if soc is not None else None,
            "target": round(target) if target is not None else None,
            "km": km_of(g("car_range")) if options.get("car_range") else None,
            "charging": _on(g("car_charging")) if options.get("car_charging") else None,
            "plugged": _on(g("car_plug")) if options.get("car_plug") else None,
        })
    if not tiles:
        return {"state": "empty"}
    return {"state": "ok", "tiles": tiles, "time": local.strftime("%H:%M")}


# ----------------------------------------------------------------------
# The widget's own language (a cell option), whatever the dashboard's
# ----------------------------------------------------------------------
LANGUAGES = ("nl", "en", "de")


def strings_for(options: dict[str, Any]) -> tuple[str, dict[str, str]]:
    lang = str(options.get("language") or "auto")
    if lang not in LANGUAGES:
        return "", {}
    try:
        got = json.loads((_HERE / "strings" / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return lang, {}
    return lang, got if isinstance(got, dict) else {}


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any], **kw: Any) -> dict[str, Any]:
    data = _fetch(options, settings, ctx=ctx, **kw)
    lang, strings = strings_for(options)
    if lang and isinstance(data, dict):
        data["lang"], data["strings"] = lang, strings
    return data
