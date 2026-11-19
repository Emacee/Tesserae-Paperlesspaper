"""agenda_list: the next days as a list, with the drive time to each event's
location worked out by Waze through Home Assistant.

Events come from the Calendar Core plugin (Settings › Widgets › Calendar
Feeds). For a timed event that has a location and has not started yet, the
widget asks Home Assistant's ``waze_travel_time.get_travel_times`` service
for the drive from home to that location, and shows the minutes with the time
to leave: the start, minus the drive, minus a margin.

Nothing about the home address lives in this file: it is a cell option (kept
with the page, never in an exported template), and defaults to the Home
Assistant zone ``zone.home``.

Answers are kept in memory for a while (long for events days away, short for
an event that is soon), so a page that redraws every few minutes does not ask
Waze every time. A location Waze cannot find is remembered as not found for a
little while, and the event is shown without a drive.
"""

from __future__ import annotations

import contextlib
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_LOOKUPS = 12  # Waze questions per fetch, the rest wait for the next one
SOON_H = 3  # an event this close gets a live (traffic) answer, kept briefly
TTL_SOON_S = 10 * 60
TTL_FAR_S = 6 * 3600
TTL_MISS_S = 30 * 60
WAZE_TIMEOUT_S = 20

_cache: dict[tuple[str, str, bool], tuple[float, float | None]] = {}
_lock = threading.Lock()


# ----------------------------------------------------------------------
# Plugins we lean on
# ----------------------------------------------------------------------
def _plugin(name: str) -> Any:
    with contextlib.suppress(Exception):
        from flask import current_app

        return current_app.config["PLUGIN_REGISTRY"].get(name)
    return None


def _zone(options: dict[str, Any]) -> Any:
    with contextlib.suppress(Exception):
        from app.tz_resolve import app_timezone

        return app_timezone()
    name = str(options.get("timezone") or "")
    if name:
        with contextlib.suppress(Exception):
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
    return timezone.utc


# ----------------------------------------------------------------------
# Waze
# ----------------------------------------------------------------------
def _minutes(response: Any) -> float | None:
    """The shortest route's minutes in a get_travel_times response."""
    body = response.get("service_response", response) if isinstance(response, dict) else {}
    routes = body.get("routes") if isinstance(body, dict) else None
    best = None
    for route in routes or []:
        try:
            m = float(route.get("duration"))
        except (AttributeError, TypeError, ValueError):
            continue
        if m >= 0 and (best is None or m < best):
            best = m
    return best


def drive_minutes(core: Any, origin: str, destination: str, region: str, soon: bool, *, now: float | None = None) -> float | None:
    """Minutes by car from origin to destination, from the cache or Waze."""
    now = time.time() if now is None else now
    key = (origin, destination.strip().lower(), soon)
    with _lock:
        hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    try:
        minutes = _minutes(
            core.call_service_with_response(
                "waze_travel_time",
                "get_travel_times",
                data={
                    "origin": origin,
                    "destination": destination,
                    "region": region,
                    "units": "metric",
                    "vehicle_type": "car",
                    "realtime": soon,
                },
                timeout=WAZE_TIMEOUT_S,
            )
        )
    except Exception:  # noqa: BLE001 - Waze not set up, address not found, HA down
        minutes = None
    ttl = TTL_MISS_S if minutes is None else (TTL_SOON_S if soon else TTL_FAR_S)
    with _lock:
        _cache[key] = (now + ttl, minutes)
    return minutes


def leave_at(start: datetime, minutes: float, margin_min: int) -> datetime:
    """When to leave: the start minus the drive (rounded up) and the margin."""
    return start - timedelta(minutes=math.ceil(minutes) + margin_min)


# ----------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------
def _dt(value: Any, zone: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(zone)


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _flag(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() not in ("false", "0", "off", "no")


def build_days(
    events: list[dict[str, Any]], today: date, days: int, zone: Any, *, symbols: bool
) -> list[dict[str, Any]]:
    """Per day: all-day events (a multi-day one once, on its first visible day,
    with the day it runs through) and timed events in order of start."""
    out = [{"date": (today + timedelta(days=i)).isoformat(), "weekday": (today + timedelta(days=i)).weekday(),
            "day": (today + timedelta(days=i)).day, "is_today": i == 0, "all_day": [], "events": []} for i in range(days)]
    index = {d["date"]: d for d in out}
    last = today + timedelta(days=days - 1)

    def title(ev: dict[str, Any]) -> str:
        summary = str(ev.get("summary") or "").strip()
        symbol = str(ev.get("feed_symbol") or "").strip() if symbols else ""
        return f"{symbol} {summary}".strip() if symbol else summary

    for ev in events:
        colour = ev.get("feed_colour") or ""
        if ev.get("all_day"):
            first = _date(ev.get("start"))
            end_excl = _date(ev.get("end")) or (first + timedelta(days=1) if first else None)
            if first is None or end_excl is None:
                continue
            through = end_excl - timedelta(days=1)
            shown = max(first, today)
            row = index.get(shown.isoformat())
            if row is None or through < today or shown > last:
                continue
            item = {"title": title(ev), "colour": colour}
            if through > shown:
                item["through"] = min(through, last).isoformat()
                item["through_weekday"] = min(through, last).weekday()
            row["all_day"].append(item)
            continue
        start = _dt(ev.get("start"), zone)
        if start is None:
            continue
        end = _dt(ev.get("end"), zone) or start
        row = index.get(start.date().isoformat())
        if row is None:
            continue
        row["events"].append({
            "title": title(ev),
            "colour": colour,
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M"),
            "location": str(ev.get("location") or "").strip(),
            "_start": start,
        })
    for row in out:
        row["events"].sort(key=lambda e: (e["_start"], e["title"]))
    return out


def add_travel(
    rows: list[dict[str, Any]], core: Any, options: dict[str, Any], now: datetime
) -> bool:
    """Put {"min", "leave"} on timed events with a location that are still to
    come. Returns whether Waze answered for at least one (or none was asked)."""
    origin = str(options.get("origin") or "").strip() or "zone.home"
    region = str(options.get("region") or "EU").strip() or "EU"
    margin = _int(options.get("margin_min"), 5, 0, 60)
    horizon = _int(options.get("travel_days"), 7, 1, 14)
    asks = []
    for row in rows[:horizon]:
        for ev in row["events"]:
            if ev["location"] and ev["_start"] > now:
                asks.append(ev)
    asks = asks[:MAX_LOOKUPS]
    if not asks:
        return True

    def one(ev: dict[str, Any]) -> float | None:
        soon = ev["_start"] - now < timedelta(hours=SOON_H)
        return drive_minutes(core, origin, ev["location"], region, soon)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, asks))
    for ev, minutes in zip(asks, results):
        if minutes is not None:
            ev["travel"] = {"min": math.ceil(minutes), "leave": leave_at(ev["_start"], minutes, margin).strftime("%H:%M")}
    return any(m is not None for m in results)


# ----------------------------------------------------------------------
# The widget's own language (a cell option), whatever the dashboard's
# ----------------------------------------------------------------------
LANGUAGES = ("nl", "en", "de")


def strings_for(options: dict[str, Any]) -> tuple[str, dict[str, str]]:
    lang = str(options.get("language") or "auto")
    if lang not in LANGUAGES:
        return "", {}
    try:
        got = json.loads((Path(__file__).resolve().parent / "strings" / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return lang, {}
    return lang, got if isinstance(got, dict) else {}


def _fetch(
    options: dict[str, Any],
    settings: dict[str, Any],
    *,
    ctx: dict[str, Any],
    now: datetime | None = None,
    cal: Any = None,
    core: Any = None,
) -> dict[str, Any]:
    del settings, ctx
    cal = cal if cal is not None else _plugin("calendar_core")
    if cal is None or getattr(cal, "server_module", None) is None:
        return {"error": "Install the Calendar Core plugin to use this widget.", "days": []}
    zone = _zone(options)
    now = (now or datetime.now(timezone.utc)).astimezone(zone)
    days = _int(options.get("days"), 7, 1, 14)
    today = now.date()
    start = datetime.combine(today, datetime.min.time(), zone)
    end = datetime.combine(today + timedelta(days=days), datetime.min.time(), zone)
    feeds = [f.strip() for f in str(options.get("feeds_filter") or "").split(",") if f.strip()] or None
    try:
        events = cal.server_module.load_events(
            feeds, start.astimezone(timezone.utc), end.astimezone(timezone.utc), data_dir=Path(cal.data_dir)
        )
    except Exception as err:  # noqa: BLE001
        return {"error": f"{type(err).__name__}: {err}", "days": []}

    rows = build_days(events, today, days, zone, symbols=_flag(options.get("show_symbol"), False))
    travel = "off"
    if _flag(options.get("show_travel"), True):
        core = core if core is not None else (getattr(_plugin("ha_core"), "server_module", None))
        if core is None:
            travel = "no_core"
        else:
            travel = "ok" if add_travel(rows, core, options, now) else "unavailable"
    for row in rows:
        for ev in row["events"]:
            ev.pop("_start", None)
    return {
        "title": " ".join(str(options.get("title") or "").split()),
        "margin": _int(options.get("margin_min"), 5, 0, 60),
        "travel": travel,
        "days": rows,
    }


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any], **kw: Any) -> dict[str, Any]:
    data = _fetch(options, settings, ctx=ctx, **kw)
    lang, strings = strings_for(options)
    if lang and isinstance(data, dict):
        data["lang"], data["strings"] = lang, strings
    return data
