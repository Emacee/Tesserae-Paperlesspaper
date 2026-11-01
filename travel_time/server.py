"""travel_time: travel time to work in the morning, home in the afternoon.

Reads travel-time sensors from Home Assistant through the Home Assistant
Core plugin (Waze Travel Time, Google Maps Travel Time, or any sensor in
minutes). Up to three people, each with a sensor for the way to work and
one for the way home. Before the switch hour the page shows the way to
work, from it the way home; at the weekend the cell stays empty unless
told otherwise.

"Normal" is the median of the same sensor at the same weekday and time of
day over the last weeks, from Home Assistant's history. It is worked out
once a day per sensor, in the background, and kept in the widget's data
folder; until it is there the delay is left out.

Nothing about the people, their sensors or their addresses lives in this
file: the sensors are picked in the cell's options and kept with the page.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PEOPLE = 3
SLOT_MIN = 15  # the baseline is kept per weekday and quarter of an hour
NEIGHBOURS = 1  # a quarter either side counts, so a thin history still has a value
MIN_SAMPLES = 3  # fewer than this at a moment: no "normal" for it
HISTORY_TIMEOUT_S = 25
BASELINE_TTL_S = 20 * 3600

_building: set[str] = set()
_building_lock = threading.Lock()


# ----------------------------------------------------------------------
# Home Assistant Core
# ----------------------------------------------------------------------
def _core() -> Any:
    with contextlib.suppress(Exception):
        from flask import current_app

        plugin = current_app.config["PLUGIN_REGISTRY"].get("ha_core")
        return plugin.server_module if plugin is not None else None
    return None


def _is_travel_sensor(st: dict[str, Any]) -> bool:
    eid = str(st.get("entity_id") or "")
    if not eid.startswith("sensor."):
        return False
    attrs = st.get("attributes") or {}
    unit = str(attrs.get("unit_of_measurement") or "").lower()
    return attrs.get("device_class") == "duration" or unit in ("min", "minutes", "minuten")


def _is_waze(st: dict[str, Any]) -> bool:
    attrs = st.get("attributes") or {}
    return "waze" in str(attrs.get("attribution") or "").lower() or "waze" in str(st.get("entity_id") or "")


def choices(name: str) -> list[dict[str, str]]:
    """The editor's sensor dropdowns: travel-time sensors only, Waze first,
    each with its current value so the right one is easy to spot."""
    core = _core()
    if name != "travel_sensor" or core is None:
        return []
    if not core.is_configured():
        return [{"value": "", "label": "Set HA URL + token in Settings → Widgets → Home Assistant Core"}]
    try:
        states = core.get_states()
    except Exception:  # noqa: BLE001 - the dropdown explains itself instead
        return [{"value": "", "label": "Home Assistant unreachable, check URL + token"}]
    rows = []
    for st in states:
        if not isinstance(st, dict) or not _is_travel_sensor(st):
            continue
        eid = str(st["entity_id"])
        friendly = core.friendly_name(st)
        value = _minutes(st.get("state"))
        now = f" · {round(value)} min" if value is not None else ""
        rows.append((0 if _is_waze(st) else 1, friendly.lower(), {"value": eid, "label": f"{friendly}{now} ({eid})"}))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [{"value": "", "label": "—"}] + [r[2] for r in rows]


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
def _minutes(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0 < v < 24 * 60 else None


def roads(route: Any) -> list[str]:
    """Road numbers from a Waze route ("A2 - E35; A12 - E30 - E35" -> A2, A12):
    the national ones (A, N, S) in order, each once; E-roads only when there
    is nothing else."""
    text = str(route or "")
    found = re.findall(r"\b([ANS]\d{1,3}|E\d{1,3})\b", text)
    out: list[str] = []
    for r in found:
        if r not in out:
            out.append(r)
    national = [r for r in out if not r.startswith("E")]
    return (national or out)[:3]


def _local(now: datetime | None, options: dict[str, Any]) -> datetime:
    tz = None
    name = str(options.get("timezone") or "")
    if name:
        with contextlib.suppress(Exception):
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(name)
    now = now or datetime.now(timezone.utc)
    return now.astimezone(tz) if tz else now.astimezone()


def slot_of(dt: datetime) -> tuple[int, int]:
    return dt.weekday(), (dt.hour * 60 + dt.minute) // SLOT_MIN


def _key(entity_id: str) -> str:
    return hashlib.sha1(entity_id.encode()).hexdigest()[:12]


# ----------------------------------------------------------------------
# The baseline: median per weekday and quarter of an hour
# ----------------------------------------------------------------------
def build_baseline(samples: list[dict[str, Any]], tz: Any, end: datetime) -> dict[str, float]:
    """``samples`` as HA's minimal history gives them ({state, last_changed}):
    each value counts for every quarter of an hour it was the state, so a
    value that held for an hour counts four times, and a sensor that is
    only written when it changes still fills the table."""
    per: dict[str, list[float]] = {}
    parsed: list[tuple[datetime, float]] = []
    for s in samples:
        v = _minutes(s.get("state"))
        t = str(s.get("last_changed") or s.get("last_updated") or "")
        if v is None or not t:
            continue
        with contextlib.suppress(ValueError):
            parsed.append((datetime.fromisoformat(t.replace("Z", "+00:00")), v))
    parsed.sort(key=lambda p: p[0])
    for i, (t0, v) in enumerate(parsed):
        t1 = parsed[i + 1][0] if i + 1 < len(parsed) else end
        # a value is not trusted for more than two hours: a sensor that stopped
        # polling at night would otherwise speak for the whole night
        t1 = min(t1, t0 + timedelta(hours=2))
        q = t0.replace(minute=t0.minute - t0.minute % SLOT_MIN, second=0, microsecond=0)
        while q < t1:
            if q + timedelta(minutes=SLOT_MIN) > t0:
                wd, sl = slot_of(q.astimezone(tz) if tz else q.astimezone())
                per.setdefault(f"{wd}-{sl}", []).append(v)
            q += timedelta(minutes=SLOT_MIN)
    return {k: round(statistics.median(vs), 1) for k, vs in per.items() if vs}


def normal_at(table: dict[str, Any], counts: dict[str, Any] | None, dt: datetime) -> float | None:
    """The median for this weekday and quarter, with the quarters either side
    when this one has too few samples."""
    wd, sl = slot_of(dt)
    per_day = 24 * 60 // SLOT_MIN
    vals = []
    for d in range(-NEIGHBOURS, NEIGHBOURS + 1):
        k = f"{wd}-{(sl + d) % per_day}"
        if k in table:
            vals.append(float(table[k]))
    if not vals:
        return None
    if counts is not None and sum(int(counts.get(f"{wd}-{(sl + d) % per_day}", 0)) for d in range(-NEIGHBOURS, NEIGHBOURS + 1)) < MIN_SAMPLES:
        return None
    return round(statistics.median(vals), 1)


def _baseline_path(data_dir: Path, entity_id: str, weeks: int) -> Path:
    return data_dir / "baseline" / f"{_key(entity_id)}_{weeks}w.json"


def _read_baseline(path: Path) -> dict[str, Any] | None:
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and isinstance(got.get("table"), dict) else None


def _count(samples: list[dict[str, Any]], tz: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in samples:
        t = str(s.get("last_changed") or "")
        if _minutes(s.get("state")) is None or not t:
            continue
        with contextlib.suppress(ValueError):
            d = datetime.fromisoformat(t.replace("Z", "+00:00"))
            wd, sl = slot_of(d.astimezone(tz) if tz else d.astimezone())
            out[f"{wd}-{sl}"] = out.get(f"{wd}-{sl}", 0) + 1
    return out


def _refresh_baseline(core: Any, entity_id: str, weeks: int, path: Path, tz: Any) -> None:
    """Ask HA for the weeks of history and write the table. Runs on a thread
    with the app's context; one at a time per sensor."""
    try:
        samples = core.history(entity_id, hours=weeks * 7 * 24, timeout=HISTORY_TIMEOUT_S)
        end = datetime.now(timezone.utc)
        table = build_baseline(samples, tz, end)
        counts = _count(samples, tz)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"made": time.time(), "weeks": weeks, "table": table, "counts": counts}), encoding="utf-8")
    except Exception:  # noqa: BLE001 - tried again on the next render
        pass
    finally:
        with _building_lock:
            _building.discard(str(path))


def baseline_for(core: Any, entity_id: str, weeks: int, data_dir: Path, tz: Any) -> dict[str, Any] | None:
    """The kept table (even a day old), and a fresh one started when it is
    missing or stale."""
    path = _baseline_path(data_dir, entity_id, weeks)
    got = _read_baseline(path)
    stale = got is None or time.time() - float(got.get("made") or 0) > BASELINE_TTL_S
    if stale:
        with _building_lock:
            busy = str(path) in _building
            if not busy:
                _building.add(str(path))
        if not busy:
            app = None
            with contextlib.suppress(Exception):
                from flask import current_app

                app = current_app._get_current_object()

            def run() -> None:
                if app is not None:
                    with app.app_context():
                        _refresh_baseline(core, entity_id, weeks, path, tz)
                else:
                    _refresh_baseline(core, entity_id, weeks, path, tz)

            threading.Thread(target=run, name="travel-baseline", daemon=True).start()
    return got


# ----------------------------------------------------------------------
# The fetch
# ----------------------------------------------------------------------
def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _fetch(
    options: dict[str, Any],
    settings: dict[str, Any],
    *,
    ctx: dict[str, Any],
    now: datetime | None = None,
    core: Any = None,
) -> dict[str, Any]:
    del settings
    core = core if core is not None else _core()
    title = " ".join(str(options.get("title") or "").split())
    if core is None:
        return {"error": "Install the Home Assistant Core plugin to use this widget.", "title": title}

    local = _local(now, options)
    switch = _int(options.get("switch_hour"), 14, 0, 23)
    direction = "work" if local.hour < switch else "home"
    weekend = local.weekday() >= 5
    if weekend and str(options.get("weekend") or "hide") == "hide":
        return {"state": "off", "reason": "weekend", "direction": direction, "title": title}

    people = []
    for i in range(1, PEOPLE + 1):
        eid = str(options.get(f"person_{i}_to_{direction}") or "").strip()
        if not eid:
            continue
        people.append((i, str(options.get(f"person_{i}_name") or "").strip(), eid))
    if not people:
        return {"state": "empty", "direction": direction, "title": title}

    delay_min = _int(options.get("delay_min"), 2, 1, 30)
    weeks = _int(options.get("baseline_weeks"), 6, 2, 12)
    show_route = str(options.get("show_route", True)).lower() not in ("false", "0", "off", "no")
    data_dir = Path(str(ctx.get("data_dir") or "."))
    with contextlib.suppress(OSError):
        data_dir.mkdir(parents=True, exist_ok=True)
    tz = local.tzinfo

    rows = []
    for i, name, eid in people:
        try:
            st = core.get_state(eid)
        except Exception:  # noqa: BLE001 - one person's sensor down is not the cell's
            st = {}
        minutes = _minutes((st or {}).get("state"))
        attrs = (st or {}).get("attributes") or {}
        row: dict[str, Any] = {
            "n": i,
            "name": name or (core.friendly_name(st) if st else eid),
            "initial": (name or (core.friendly_name(st) if st else "?"))[:1].upper(),
            "min": round(minutes) if minutes is not None else None,
            "roads": roads(attrs.get("route")) if show_route else [],
            "km": round(float(attrs["distance"])) if isinstance(attrs.get("distance"), (int, float)) else None,
            "waze": bool(st) and _is_waze(st),
        }
        base = baseline_for(core, eid, weeks, data_dir, tz)
        if base and minutes is not None:
            normal = normal_at(base["table"], base.get("counts"), local)
            if normal is not None:
                row["normal"] = round(normal)
                late = round(minutes - normal)
                row["late"] = late if late >= delay_min else 0
        rows.append(row)

    return {
        "state": "ok",
        "direction": direction,
        "title": title,
        "time": local.strftime("%H:%M"),
        "people": rows,
        "source": "Waze" if any(r["waze"] for r in rows) else "",
    }


# ----------------------------------------------------------------------
# The widget's own language (a cell option), whatever the dashboard's
# ----------------------------------------------------------------------
LANGUAGES = ("nl", "en", "de")


def strings_for(options: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """(language, its strings) when the cell names a language, else ("", {}):
    the page then keeps the dashboard's own."""
    lang = str(options.get("language") or "auto")
    if lang not in LANGUAGES:
        return "", {}
    try:
        got = json.loads((Path(__file__).resolve().parent / "strings" / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return lang, {}
    return lang, got if isinstance(got, dict) else {}


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any], **kw: Any) -> dict[str, Any]:
    data = _fetch(options, settings, ctx=ctx, **kw)
    lang, strings = strings_for(options)
    if lang and isinstance(data, dict):
        data["lang"], data["strings"] = lang, strings
    return data
