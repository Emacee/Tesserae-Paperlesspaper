"""Dynamic (EPEX day-ahead) electricity prices for energy_dynamic_price.

Two sources:

* ``energyzero`` (default, no key): EnergyZero's public price API, the
  Dutch EPEX day-ahead market in 15-minute or hourly slots. Comes in four
  flavours (bare market price, + VAT, all-in = market + energy tax +
  purchasing fee, all-in + VAT); "all-in incl. VAT" lands within a cent
  of what the Tibber / Frank / Zonneplan apps show.
* ``tibber``: the Tibber GraphQL API with a personal access token (plugin
  settings). Returns your own contract's ``total`` price, the exact number
  the Tibber app shows.

Tomorrow's prices are published around 13:00 CET. Before that the
widget shows today only; once they are out it shows today + tomorrow.

The raw slots are cached for 15 minutes in ``data_dir`` (prices only
change once a day, but tomorrow's arrival should show up promptly).
Everything time-dependent (which slot is "now", the window, min / max)
is derived on every call, so a cached payload never shows a stale "now".
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CACHE_TTL_S = 900
HTTP_TIMEOUT_S = 6
USER_AGENT = "tesserae/0.1 (+energy_dynamic_price)"

ENERGYZERO_URL = "https://public.api.energyzero.nl/public/v1/prices"
TIBBER_URL = "https://api.tibber.com/v1-beta/gql"

# EPEX NL is settled in Dutch local time; day boundaries follow it.
NL_TZ = ZoneInfo("Europe/Amsterdam")

PRICE_TYPES = ("all_in_with_vat", "all_in", "base_with_vat", "base")
RANGES = ("auto", "today", "ahead")

# Minor-unit label per currency. EnergyZero is always EUR.
UNIT_BY_CURRENCY = {"EUR": "ct", "NOK": "øre", "SEK": "öre", "DKK": "øre"}

_TIBBER_QUERY = """
query ($res: PriceInfoResolution) {
  viewer {
    homes {
      id
      appNickname
      currentSubscription {
        priceInfo(resolution: $res) {
          today { total startsAt currency }
          tomorrow { total startsAt currency }
        }
      }
    }
  }
}
"""


class FriendlyError(Exception):
    """Error whose message is fit to show in the cell as-is."""


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------


def _cached(path: Path) -> dict[str, Any] | None:
    if not path.exists() or time.time() - path.stat().st_mtime >= CACHE_TTL_S:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _http_json(
    url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None
) -> Any:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_iso(value: str) -> datetime:
    # Python < 3.11 can't parse a trailing "Z"; normalise it.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _minutes(options: dict[str, Any]) -> int:
    return 60 if str(options.get("resolution", "15")) == "60" else 15


# ----------------------------------------------------------------------
# Sources -> list of {"start": iso-with-offset, "price": cents}
# ----------------------------------------------------------------------


def _energyzero_day_pair(day: date, minutes: int, price_type: str) -> list[dict[str, Any]]:
    """EnergyZero's ``date=D`` returns the slots of D-1 and D (local)."""
    interval = "INTERVAL_QUARTER" if minutes == 15 else "INTERVAL_HOUR"
    url = (
        f"{ENERGYZERO_URL}?date={day.strftime('%d-%m-%Y')}"
        f"&interval={interval}&energyType=ENERGY_TYPE_ELECTRICITY"
    )
    payload = _http_json(url)
    rows = payload.get(price_type) or []
    slots: list[dict[str, Any]] = []
    for row in rows:
        try:
            start = _parse_iso(row["start"]).astimezone(NL_TZ)
            eur = float(row["price"]["value"])
        except (KeyError, TypeError, ValueError):
            continue
        slots.append({"start": start.isoformat(), "price": eur * 100.0})
    return slots


def _fetch_energyzero(options: dict[str, Any], now: datetime) -> dict[str, Any]:
    minutes = _minutes(options)
    price_type = str(options.get("price_type", "all_in_with_vat"))
    if price_type not in PRICE_TYPES:
        price_type = "all_in_with_vat"
    today = now.astimezone(NL_TZ).date()
    try:
        # Asking for tomorrow returns today + tomorrow in one call...
        slots = _energyzero_day_pair(today + timedelta(days=1), minutes, price_type)
    except urllib.error.HTTPError as err:
        # ...but 404s until tomorrow's auction result is published.
        if err.code not in (400, 404):
            raise
        slots = _energyzero_day_pair(today, minutes, price_type)
    return {"slots": slots, "currency": "EUR", "tz": "Europe/Amsterdam"}


def _fetch_tibber(options: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    token = str(settings.get("tibber_token") or "").strip()
    if not token:
        raise FriendlyError("Add your Tibber API token in the widget settings.")
    res = "HOURLY" if _minutes(options) == 60 else "QUARTER_HOURLY"
    body = json.dumps({"query": _TIBBER_QUERY, "variables": {"res": res}}).encode()
    try:
        payload = _http_json(
            TIBBER_URL,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
    except urllib.error.HTTPError as err:
        if err.code in (400, 401, 403):
            raise FriendlyError("Tibber rejected the API token. Check it in the widget settings.") from err
        raise
    if payload.get("errors") and not payload.get("data"):
        msg = str((payload["errors"][0] or {}).get("message", ""))
        if "token" in msg.lower() or "auth" in msg.lower():
            raise FriendlyError("Tibber rejected the API token. Check it in the widget settings.")
        raise FriendlyError("Tibber couldn't return prices right now.")

    homes = ((payload.get("data") or {}).get("viewer") or {}).get("homes") or []
    wanted = str(settings.get("tibber_home_id") or "").strip()
    home = None
    for h in homes:
        if not (h or {}).get("currentSubscription"):
            continue
        if wanted and h.get("id") != wanted:
            continue
        home = h
        break
    if home is None:
        raise FriendlyError("No Tibber home with an active contract on this account.")

    info = home["currentSubscription"].get("priceInfo") or {}
    slots: list[dict[str, Any]] = []
    currency = "EUR"
    for row in (info.get("today") or []) + (info.get("tomorrow") or []):
        try:
            start = _parse_iso(row["startsAt"])
            total = float(row["total"])
        except (KeyError, TypeError, ValueError):
            continue
        slots.append({"start": start.isoformat(), "price": total * 100.0})
        currency = row.get("currency") or currency
    tz = str(settings.get("timezone") or "Europe/Amsterdam")
    return {"slots": slots, "currency": currency, "tz": tz}


# ----------------------------------------------------------------------
# Window + stats (computed fresh every call)
# ----------------------------------------------------------------------


def _fmt_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def build_view(raw: dict[str, Any], options: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Slice the raw slots to the requested window and derive now/min/max."""
    try:
        tz = ZoneInfo(str(raw.get("tz") or "Europe/Amsterdam"))
    except (ValueError, KeyError):  # ZoneInfoNotFoundError is a KeyError
        tz = NL_TZ
    now_l = now.astimezone(tz)
    today = now_l.date()
    tomorrow = today + timedelta(days=1)
    rng = str(options.get("range", "auto"))
    if rng not in RANGES:
        rng = "auto"

    parsed: list[tuple[datetime, float]] = []
    seen: set[str] = set()
    for s in raw.get("slots") or []:
        try:
            dt = _parse_iso(s["start"]).astimezone(tz)
            price = float(s["price"])
        except (KeyError, TypeError, ValueError):
            continue
        key = dt.isoformat()
        if key in seen:
            continue
        seen.add(key)
        parsed.append((dt, price))
    parsed.sort(key=lambda x: x[0])

    # Slot length from the data itself (15 or 60), fall back to the option.
    minutes = _minutes(options)
    if len(parsed) >= 2:
        step = int((parsed[1][0] - parsed[0][0]).total_seconds() // 60)
        if step in (15, 30, 60):
            minutes = step
    slot_len = timedelta(minutes=minutes)

    has_tomorrow = any(dt.date() == tomorrow for dt, _ in parsed)
    if rng == "today":
        window = [(dt, p) for dt, p in parsed if dt.date() == today]
    elif rng == "ahead":
        window = [
            (dt, p) for dt, p in parsed if dt + slot_len > now_l and dt.date() in (today, tomorrow)
        ]
    else:
        window = [(dt, p) for dt, p in parsed if dt.date() in (today, tomorrow)]

    if not window:
        return {"error": "No prices available for today yet."}

    now_idx = None
    for i, (dt, _) in enumerate(window):
        if dt <= now_l < dt + slot_len:
            now_idx = i
            break
    # Fraction of the way through the current slot, so the "now" line can
    # sit at the exact minute rather than the slot's left edge.
    now_frac = 0.0
    if now_idx is not None:
        now_frac = (now_l - window[now_idx][0]).total_seconds() / slot_len.total_seconds()

    prices = [p for _, p in window]
    # Stats over what is still to come when "now" is in the window: the
    # useful "cheapest moment" is one you can still act on. Falls back to
    # the full window when everything is in the past/future.
    stat_from = now_idx if now_idx is not None else 0
    if str(options.get("stats_scope", "upcoming")) == "window":
        stat_from = 0
    upcoming = list(range(stat_from, len(window)))
    i_min = min(upcoming, key=lambda i: (prices[i], i))
    i_max = max(upcoming, key=lambda i: (prices[i], -i))

    def _mark(i: int) -> dict[str, Any]:
        dt = window[i][0]
        return {
            "i": i,
            "p": round(prices[i], 2),
            "t": _fmt_hhmm(dt),
            "day": "tomorrow" if dt.date() == tomorrow else "today",
        }

    days: list[dict[str, Any]] = []
    for i, (dt, _) in enumerate(window):
        key = "tomorrow" if dt.date() == tomorrow else "today"
        if not days or days[-1]["key"] != key:
            days.append({"key": key, "i": i, "date": dt.date().isoformat()})

    current = None
    if now_idx is not None:
        dt = window[now_idx][0]
        current = {
            "i": now_idx,
            "p": round(prices[now_idx], 2),
            "from": _fmt_hhmm(dt),
            "till": _fmt_hhmm(dt + slot_len),
        }

    currency = str(raw.get("currency") or "EUR")
    return {
        "minutes": minutes,
        "range": rng,
        "currency": currency,
        "unit": UNIT_BY_CURRENCY.get(currency, "ct"),
        "has_tomorrow": has_tomorrow,
        "slots": [{"t": _fmt_hhmm(dt), "p": round(p, 3)} for dt, p in window],
        "days": days,
        "now": current,
        "now_frac": round(now_frac, 3),
        "min": _mark(i_min),
        "max": _mark(i_max),
        "avg": round(sum(prices[stat_from:]) / len(prices[stat_from:]), 2),
        "updated": _fmt_hhmm(now_l),
    }


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------


def fetch(
    options: dict[str, Any],
    settings: dict[str, Any],
    *,
    ctx: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    source = str(options.get("source", "energyzero"))
    if source not in ("energyzero", "tibber"):
        source = "energyzero"
    title = str(options.get("title") or "")

    data_dir = Path(ctx["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    day = now.astimezone(NL_TZ).date().isoformat()
    if source == "tibber":
        token = str(settings.get("tibber_token") or "")
        key = f"tibber_{_minutes(options)}_{hashlib.sha256(token.encode()).hexdigest()[:10]}"
    else:
        key = f"ez_{_minutes(options)}_{options.get('price_type', 'all_in_with_vat')}"
    cache_path = data_dir / f"prices_{key}_{day}.json"

    raw = _cached(cache_path)
    if raw is None:
        try:
            if source == "tibber":
                raw = _fetch_tibber(options, settings)
            else:
                raw = _fetch_energyzero(options, now)
        except FriendlyError as err:
            return {"error": str(err), "title": title}
        except urllib.error.HTTPError as err:
            if err.code == 429:
                return {"error": "Price service is rate-limiting; retrying shortly.", "title": title}
            return {"error": "Couldn't load energy prices right now.", "title": title}
        except (urllib.error.URLError, TimeoutError, OSError):
            return {"error": "Price service unreachable. Check the network.", "title": title}
        except (ValueError, KeyError, TypeError):
            return {"error": "Price service returned something unexpected.", "title": title}
        with contextlib.suppress(OSError):
            cache_path.write_text(json.dumps(raw), encoding="utf-8")
        # Drop yesterday's cache files so data_dir doesn't grow forever.
        for old in data_dir.glob("prices_*.json"):
            if not old.name.endswith(f"_{day}.json"):
                with contextlib.suppress(OSError):
                    old.unlink()

    view = build_view(raw, options, now)
    view["title"] = title
    view["source"] = source
    return view
