"""weather_today: today's weather as a column, for a narrow portrait cell.

On top the date, the weather now (icon, temperature, what it is like), the
day's high and low and its rain in mm; under it one row per hour for the
rest of the day: icon, temperature and a bar for the rain in that hour.
Hours gone by stay, faded, from the first hour asked for.

Data from Open-Meteo (no key), cached for ten minutes per place.
"""

from __future__ import annotations

import contextlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CACHE_TTL_S = 600
STALE_OK_S = 3 * 3600  # an older forecast, shown when Open-Meteo does not answer
HTTP_TIMEOUT_S = 8
USER_AGENT = "tesserae-widget-weather-today/0.1 (+https://github.com/Emacee/Tesserae-Paperlesspaper)"

# WMO weather code -> (condition, has a night form)
WMO: dict[int, str] = {
    0: "clear", 1: "mostly_clear", 2: "partly_cloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "drizzle", 57: "drizzle",
    61: "rain", 63: "rain", 65: "heavy_rain", 66: "rain", 67: "heavy_rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "showers", 81: "showers", 82: "heavy_rain", 85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}
# the icon for a condition, by day and by night
ICONS: dict[str, tuple[str, str]] = {
    "clear": ("sun", "moon"),
    "mostly_clear": ("sun", "moon"),
    "partly_cloudy": ("sun_cloud", "moon_cloud"),
    "cloudy": ("cloud", "cloud"),
    "fog": ("fog", "fog"),
    "drizzle": ("rain", "rain"),
    "rain": ("rain", "rain"),
    "heavy_rain": ("heavy_rain", "heavy_rain"),
    "showers": ("showers", "rain"),
    "snow": ("snow", "snow"),
    "storm": ("storm", "storm"),
}


def condition(code: Any) -> str:
    try:
        return WMO.get(int(code), "cloudy")
    except (TypeError, ValueError):
        return "cloudy"


def icon(cond: str, is_day: bool) -> str:
    day, night = ICONS.get(cond, ("cloud", "cloud"))
    return day if is_day else night


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def _get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode("utf-8"))


def _cached(path: Path, max_age_s: float = CACHE_TTL_S) -> dict[str, Any] | None:
    try:
        if time.time() - path.stat().st_mtime > max_age_s:
            return None
        got = json.loads(path.read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def build_view(raw: dict[str, Any], from_hour: int, units: str) -> dict[str, Any]:
    """The page from Open-Meteo's answer (``timezone=auto``, so its times are
    the place's own)."""
    cur = raw.get("current") or {}
    hourly = raw.get("hourly") or {}
    daily = raw.get("daily") or {}
    now_iso = str(cur.get("time") or "")
    today = now_iso[:10] or (str((daily.get("time") or [""])[0]))
    now_h = int(now_iso[11:13]) if len(now_iso) >= 13 and now_iso[11:13].isdigit() else 0

    hours = []
    times = hourly.get("time") or []
    for i, iso in enumerate(times):
        if not isinstance(iso, str) or iso[:10] != today:
            continue
        h = int(iso[11:13])
        if h < from_hour:
            continue
        cond = condition((hourly.get("weather_code") or [None] * len(times))[i])
        is_day = bool((hourly.get("is_day") or [1] * len(times))[i])
        hours.append({
            "h": h,
            "t": _round((hourly.get("temperature_2m") or [None] * len(times))[i]),
            "mm": round(_num((hourly.get("precipitation") or [0] * len(times))[i]) or 0.0, 1),
            "p": int((hourly.get("precipitation_probability") or [0] * len(times))[i] or 0),
            "icon": icon(cond, is_day),
            "past": h < now_h,
            "now": h == now_h,
        })

    def day0(key: str) -> Any:
        vals = daily.get(key) or []
        return vals[0] if vals else None

    day_cond = condition(day0("weather_code"))
    cur_cond = condition(cur.get("weather_code"))
    # the headline: what the day brings when it rains today, what it is now otherwise
    head_cond = day_cond if day_cond in ("showers", "rain", "heavy_rain", "drizzle", "snow", "storm") else cur_cond
    is_day = bool(cur.get("is_day", 1))
    return {
        "date": today,
        "now": {
            "t": _round(cur.get("temperature_2m")),
            "cond": head_cond,
            "icon": icon(head_cond, is_day),
        },
        "max": _round(day0("temperature_2m_max")),
        "min": _round(day0("temperature_2m_min")),
        "mm": round(_num(day0("precipitation_sum")) or 0.0, 1),
        "p_max": int(day0("precipitation_probability_max") or 0),
        "hours": hours,
        "unit": "°F" if units == "imperial" else "°",
        "updated": now_iso[11:16],
    }


def _round(v: Any) -> int | None:
    n = _num(v)
    return int(round(n)) if n is not None else None


def _fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
    del settings
    label = str(options.get("label") or "")
    lat_raw, lon_raw = options.get("latitude"), options.get("longitude")
    if lat_raw in (None, "") or lon_raw in (None, ""):
        return {"error": "Pick a place in the cell's options.", "label": label}
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        return {"error": "The place has no valid coordinates.", "label": label}
    units = "imperial" if str(options.get("units")) == "imperial" else "metric"
    try:
        from_hour = max(0, min(23, int(options.get("from_hour", 7))))
    except (TypeError, ValueError):
        from_hour = 7

    data_dir = Path(str(ctx.get("data_dir") or "."))
    with contextlib.suppress(OSError):
        data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"today_{lat:.3f}_{lon:.3f}_{units}.json"
    raw = _cached(path)
    if raw is None:
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
            "current": "temperature_2m,weather_code,is_day",
            "hourly": "temperature_2m,precipitation,precipitation_probability,weather_code,is_day",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
            "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
        })
        try:
            raw = _get_json(f"https://api.open-meteo.com/v1/forecast?{q}")
        except Exception as err:  # noqa: BLE001 - the cell says so
            # Open-Meteo has a hiccup now and then: keep showing today's last
            # forecast (up to three hours old) rather than an error on the panel.
            raw = _cached(path, STALE_OK_S)
            if raw is None:
                return {"error": f"Weather unavailable right now ({type(err).__name__}).", "label": label}
            view = build_view(raw, from_hour, units)
            view["label"] = label
            return view
        with contextlib.suppress(OSError):
            path.write_text(json.dumps(raw), encoding="utf-8")
    view = build_view(raw, from_hour, units)
    view["label"] = label
    return view


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
