"""agenda_list: the next days as a list, with the drive time to each event's
location worked out by Waze through Home Assistant.

Events come from the Calendar Core plugin (Settings › Widgets › Calendar
Feeds). For a timed event that has a location and has not started yet, the
widget asks Home Assistant's ``waze_travel_time.get_travel_times`` service
for the drive from home to that location, and shows the minutes with the time
to leave: the start, minus the drive, minus a margin.

When Waze does not answer (or the cell says so), the drive comes from the free
OSRM routing service instead, with the places found by OpenStreetMap's
Nominatim. That has no live traffic, so a surcharge (a cell option, 15% by
default) is added and the drive shows with a ≈. Only the home position and the
event locations leave the house for those two services, with a generic client
name; nothing else.

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
import re
import threading
import time
import urllib.parse
import urllib.request
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

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=false"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "tesserae-agenda-list/0.1"  # generic: nothing about the user
HTTP_TIMEOUT_S = 10
GEOCODE_PER_FETCH = 6  # new places looked up per refresh (1 request a second is Nominatim's rule)
GEOCODE_MISS_TTL_S = 6 * 3600
WAZE_DOWN_S = 10 * 60  # after Waze failed and OSRM answered, go straight to OSRM for a while

# (origin, destination, soon) -> (valid until, minutes or None, "waze" | "osrm" | "")
_cache: dict[tuple[str, str, bool], tuple[float, float | None, str]] = {}
_geo: dict[str, list[Any]] = {}  # place -> [lat, lon] or [] for not found (with "_t" in _geo_t)
_geo_t: dict[str, float] = {}
_geo_loaded: set[str] = set()
_waze_down = [0.0]
_lock = threading.Lock()
_geo_lock = threading.Lock()
_last_geo = [0.0]


# ----------------------------------------------------------------------
# Plugins we lean on
# ----------------------------------------------------------------------
def _plugin(name: str) -> Any:
    with contextlib.suppress(Exception):
        from flask import current_app

        return current_app.config["PLUGIN_REGISTRY"].get(name)
    return None


def _app_context() -> Any:
    """A way to enter the current Flask application context again in another
    thread. Home Assistant Core reads its settings through ``current_app``,
    which exists only in the thread that is serving the request."""
    with contextlib.suppress(Exception):
        from flask import current_app

        return current_app._get_current_object().app_context  # noqa: SLF001 - the documented way to hand it on
    return contextlib.nullcontext


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


_last_error = [""]
_trace: list[str] = []  # why drives were not found, for the note at the bottom


def _why(msg: str) -> None:
    if msg not in _trace and len(_trace) < 4:
        _trace.append(msg[:120])


def _get_json(url: str) -> Any:
    """GET a URL, parsed JSON, or None (the reason is kept in _last_error).
    Goes through Tesserae's own guarded fetch when it is there, which is what
    its other widgets use; only a generic client name is sent."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        try:
            from app.net_guard import fetch_json  # Tesserae's SSRF-guarded fetch
        except ImportError:
            fetch_json = None
        if fetch_json is not None:
            return fetch_json(url, headers=headers, timeout=HTTP_TIMEOUT_S)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # noqa: S310 - fixed https hosts
            return json.loads(resp.read().decode("utf-8"))
    except Exception as err:  # noqa: BLE001 - offline, blocked, a bad answer
        _last_error[0] = f"{type(err).__name__}: {err}"[:200]
        return None


_COORDS = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def _geo_path(data_dir: Path | None) -> Path | None:
    return data_dir / "geocode.json" if data_dir else None


def _geo_load(data_dir: Path | None) -> None:
    path = _geo_path(data_dir)
    key = str(path)
    if path is None or key in _geo_loaded:
        return
    _geo_loaded.add(key)
    with contextlib.suppress(OSError, ValueError):
        for place, got in json.loads(path.read_text(encoding="utf-8")).items():
            if isinstance(got, list) and len(got) == 2:
                _geo.setdefault(place, got)


def _geo_save(data_dir: Path | None) -> None:
    path = _geo_path(data_dir)
    if path is None:
        return
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: v for k, v in _geo.items() if v}), encoding="utf-8")


_POSTCODE_NL = re.compile(r"\b(\d{4}\s?[A-Za-z]{2})\b")
_NUMBER_LETTER = re.compile(r"\b(\d+)\s?[A-Za-z]\b")


def _candidates(place: str) -> list[str]:
    """What to ask OpenStreetMap, best first. A venue name in front of an
    address ("Omakase Amsterdam, Ferdinand Bolstraat 11H, 1072 LK") often finds
    nothing and the address does; "11H" is found as "11"; a Dutch postcode alone
    still puts the drive within a kilometre or so."""
    parts = [p.strip() for p in place.split(",") if p.strip()]
    out = [", ".join(parts) if parts else place]
    if len(parts) > 2:
        out.append(", ".join(parts[1:]))
    base = out[-1]
    plain = _NUMBER_LETTER.sub(r"\1", base)
    if plain != base:
        out.append(plain)
    m = _POSTCODE_NL.search(place)
    if m:
        out.append(m.group(1))
    seen: list[str] = []
    for q in out:
        if q and q not in seen:
            seen.append(q)
    return seen[:4]


def geocode(place: str, near: tuple[float, float] | None, budget: list[int], data_dir: Path | None = None, *, now: float | None = None) -> tuple[float, float] | None:
    """Latitude and longitude of a place, from the cache or OpenStreetMap.
    A place found is kept for good (and on disk), one not found for a while.
    At most budget[0] places are looked up over the network per refresh, one
    a second; the rest are tried on the next refresh."""
    now = time.time() if now is None else now
    key = " ".join(place.lower().split())
    _geo_load(data_dir)
    with _geo_lock:
        got = _geo.get(key)
        if got:
            return float(got[0]), float(got[1])
        if got == [] and _geo_t.get(key, 0) > now:
            return None
        if budget[0] <= 0:
            _why("place lookups wait for the next refresh")
            return None
        budget[0] -= 1
        wait = _last_geo[0] + 1.1 - time.time()
        if wait > 0:
            time.sleep(wait)
        found = []
        for i, query in enumerate(_candidates(place)):
            if i and budget[0] <= 0:
                break
            if i:
                budget[0] -= 1
            wait = _last_geo[0] + 1.1 - time.time()
            if wait > 0 and i:
                time.sleep(wait)
            params = {"q": query, "format": "jsonv2", "limit": "1"}
            if near:
                lat, lon = near
                params["viewbox"] = f"{lon - 1.5},{lat + 1.5},{lon + 1.5},{lat - 1.5}"  # prefer what is near home
            hits = _get_json(f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}")
            _last_geo[0] = time.time()
            try:
                found = [round(float(hits[0]["lat"]), 6), round(float(hits[0]["lon"]), 6)]
                break
            except (TypeError, KeyError, IndexError, ValueError):
                found = []
        if not found:
            _why(f"place not found: {place[:40]}")
        _geo[key] = found
        _geo_t[key] = now + GEOCODE_MISS_TTL_S
        if found:
            _geo_save(data_dir)
    return (found[0], found[1]) if found else None


def home_position(origin: str, core: Any, budget: list[int], data_dir: Path | None) -> tuple[float, float] | None:
    """Where the drive starts: latitude,longitude as typed, a Home Assistant
    zone or device (its position), or an address."""
    m = _COORDS.match(origin)
    if m:
        return float(m.group(1)), float(m.group(2))
    if _ENTITY.match(origin):
        try:
            attrs = (core.get_state(origin) or {}).get("attributes") or {}
            return float(attrs["latitude"]), float(attrs["longitude"])
        except Exception as err:  # noqa: BLE001 - not a zone, no position
            _why(f"home {origin}: {type(err).__name__}: {err}")
            return None
    return geocode(origin, None, budget, data_dir)


def osrm_minutes(a: tuple[float, float], b: tuple[float, float], extra_pct: int) -> float | None:
    """Minutes by car from a to b without traffic, plus the surcharge."""
    url = OSRM_URL.format(a=f"{a[1]},{a[0]}", b=f"{b[1]},{b[0]}")
    body = _get_json(url)
    try:
        seconds = float(body["routes"][0]["duration"])
    except (TypeError, KeyError, IndexError, ValueError):
        _why("OSRM found no route")
        return None
    return seconds / 60.0 * (1 + extra_pct / 100.0)


def _waze(core: Any, origin: str, destination: str, region: str, soon: bool) -> float | None:
    try:
        return _minutes(
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
    except Exception as err:  # noqa: BLE001 - Waze not set up, address not found, HA down
        _why(f"Waze: {type(err).__name__}: {err}")
        return None


def drive_minutes(
    core: Any,
    origin: str,
    destination: str,
    region: str,
    soon: bool,
    *,
    source: str = "auto",
    extra_pct: int = 15,
    budget: list[int] | None = None,
    data_dir: Path | None = None,
    now: float | None = None,
) -> tuple[float | None, str]:
    """(minutes by car, "waze" or "osrm"), from the cache or the services.
    source: "waze", "osrm", or "auto" (Waze, and OSRM when Waze does not answer)."""
    now = time.time() if now is None else now
    budget = budget if budget is not None else [GEOCODE_PER_FETCH]
    key = (f"{origin}|{source}|{extra_pct}", destination.strip().lower(), soon)
    with _lock:
        hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1], hit[2]
    minutes, via = None, ""
    if source in ("auto", "waze") and not (source == "auto" and _waze_down[0] > now):
        minutes = _waze(core, origin, destination, region, soon) if core is not None else None
        via = "waze" if minutes is not None else ""
        if minutes is None and source == "auto":
            _waze_down[0] = now + WAZE_DOWN_S
    if minutes is None and source in ("auto", "osrm"):
        a = home_position(origin, core, budget, data_dir)
        if a is None and not any(t.startswith("home") for t in _trace):
            _why(f"home position unknown: {origin}" + ("" if core is not None else " (no Home Assistant Core)"))
        b = geocode(destination, a, budget, data_dir) if a else None
        if a and b:
            minutes = osrm_minutes(a, b, extra_pct)
            via = "osrm" if minutes is not None else ""
            if minutes is not None and source == "auto":
                _waze_down[0] = max(_waze_down[0], now + WAZE_DOWN_S)
    if minutes is None and (budget[0] <= 0 and source != "waze"):
        ttl = 60  # looked up later, when the next refresh has budget
    elif minutes is None:
        ttl = TTL_MISS_S
    else:
        ttl = TTL_SOON_S if soon else TTL_FAR_S
    with _lock:
        _cache[key] = (now + ttl, minutes, via)
    return minutes, via


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
            "location": ", ".join(p.strip() for p in str(ev.get("location") or "").splitlines() if p.strip()),
            "_start": start,
        })
    for row in out:
        row["events"].sort(key=lambda e: (e["_start"], e["title"]))
    return out


def add_travel(
    rows: list[dict[str, Any]], core: Any, options: dict[str, Any], now: datetime, data_dir: Path | None = None
) -> str:
    """Put {"min", "leave", "est"} on timed events with a location that are
    still to come. Returns where the drives came from: "waze", "osrm", "" (none
    found) or "none" (nothing to ask)."""
    origin = str(options.get("origin") or "").strip() or "zone.home"
    region = (str(options.get("region") or "eu").strip() or "eu").lower()  # Home Assistant wants it in lower case
    source = str(options.get("travel_source") or "auto")
    source = source if source in ("auto", "waze", "osrm") else "auto"
    extra = _int(options.get("osrm_extra_pct"), 15, 0, 100)
    margin = _int(options.get("margin_min"), 5, 0, 60)
    horizon = _int(options.get("travel_days"), 7, 1, 14)
    asks = []
    for row in rows[:horizon]:
        for ev in row["events"]:
            if ev["location"] and ev["_start"] > now:
                asks.append(ev)
    asks = asks[:MAX_LOOKUPS]
    if not asks:
        return "none"
    budget = [GEOCODE_PER_FETCH]
    app_context = _app_context()

    def one(ev: dict[str, Any]) -> tuple[float | None, str]:
        soon = ev["_start"] - now < timedelta(hours=SOON_H)
        with app_context():  # the worker thread has none of its own
            return drive_minutes(core, origin, ev["location"], region, soon, source=source, extra_pct=extra, budget=budget, data_dir=data_dir)

    # Waze can be asked in parallel; OpenStreetMap is asked one place a second,
    # so with it in play the asks go one by one.
    workers = 4 if source == "waze" else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, asks))
    vias = set()
    for ev, (minutes, via) in zip(asks, results):
        if minutes is not None:
            vias.add(via)
            ev["travel"] = {"min": math.ceil(minutes), "leave": leave_at(ev["_start"], minutes, margin).strftime("%H:%M"), "est": via == "osrm"}
    if not vias:
        return ""
    return "osrm" if vias == {"osrm"} else ("waze" if vias == {"waze"} else "mixed")


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
    del settings
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
    del _trace[:]
    _last_error[0] = ""
    travel, via = "off", ""
    if _flag(options.get("show_travel"), True):
        source = str(options.get("travel_source") or "auto")
        core = core if core is not None else (getattr(_plugin("ha_core"), "server_module", None))
        data_dir = Path(str(ctx.get("data_dir"))) if ctx.get("data_dir") else None
        if core is None and source == "waze":
            travel = "no_core"
        else:
            via = add_travel(rows, core, options, now, data_dir)
            travel = "unavailable" if via == "" else "ok"
    for row in rows:
        for ev in row["events"]:
            ev.pop("_start", None)
    return {
        "title": " ".join(str(options.get("title") or "").split()),
        "margin": _int(options.get("margin_min"), 5, 0, 60),
        "travel": travel,
        "via": via,
        "why": "; ".join(_trace + ([_last_error[0]] if _last_error[0] else [])) if travel == "unavailable" else "",
        "days": rows,
    }


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any], **kw: Any) -> dict[str, Any]:
    data = _fetch(options, settings, ctx=ctx, **kw)
    lang, strings = strings_for(options)
    if lang and isinstance(data, dict):
        data["lang"], data["strings"] = lang, strings
    return data
