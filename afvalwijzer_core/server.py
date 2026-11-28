"""afvalwijzer_core: the collection dates of Mijn Afvalwijzer, for the waste widgets.

Asks the web service behind mijnafvalwijzer.nl for the dates at one address
(postcode and house number, set once under Settings › Widgets) and keeps the
answer for twelve hours, in memory and on disk, so the widgets that redraw every
few minutes do not ask again, and a service that is down for a day does not
empty them. The address is only sent to mijnafvalwijzer.nl.

The service is unofficial: it is what the Mijn Afvalwijzer app and website use.
Other widgets read it through ``pickups()``.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

API_URL = "https://api.mijnafvalwijzer.nl/webservices/appsinput/"
USER_AGENT = "tesserae-afvalwijzer/0.1"  # generic: nothing about the user
TTL_S = 12 * 3600
TIMEOUT_S = 15

_lock = threading.Lock()
_memory: dict[str, tuple[float, list[dict[str, str]]]] = {}


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
PLUGIN_ID = "afvalwijzer_core"


def _manifest_settings() -> list[dict[str, Any]]:
    with contextlib.suppress(OSError, ValueError):
        got = json.loads((_HERE / "plugin.json").read_text(encoding="utf-8")).get("settings")
        return got if isinstance(got, list) else []
    return []


def default_key() -> str:
    """The service key in the manifest's settings, for a blank one."""
    for f in _manifest_settings():
        if f.get("name") == "api_key":
            return str(f.get("default") or "")
    return ""


def _settings() -> dict[str, Any]:
    """The plugin's settings, secrets decrypted, the way Tesserae's settings form stores them."""
    with contextlib.suppress(Exception):
        from flask import current_app

        store = current_app.config["SETTINGS_STORE"]
        with contextlib.suppress(Exception):
            got = store.get_for_runtime("plugins", PLUGIN_ID, _manifest_settings())
            if isinstance(got, dict) and got:
                return got
        return (store.get_section("plugins") or {}).get(PLUGIN_ID) or {}
    return {}


def _secret(s: dict[str, Any], name: str) -> str:
    return str(s.get(f"{name}_secret") or s.get(name) or "").strip()


def address(settings: dict[str, Any] | None = None) -> dict[str, str]:
    """The address from the settings: postcode (no space, capitals), house number, addition, key."""
    s = _settings() if settings is None else settings
    postcode = re.sub(r"\s+", "", _secret(s, "postcode")).upper()
    number = re.sub(r"\D", "", _secret(s, "huisnummer"))
    return {
        "postcode": postcode,
        "huisnummer": number,
        "toevoeging": _secret(s, "toevoeging"),
        "api_key": _secret(s, "api_key") or default_key(),
    }


def configured(settings: dict[str, Any] | None = None) -> bool:
    a = address(settings)
    return bool(re.fullmatch(r"\d{4}[A-Z]{2}", a["postcode"]) and a["huisnummer"] and a["api_key"])


# ----------------------------------------------------------------------
# The service
# ----------------------------------------------------------------------
def _get_json(url: str) -> Any:
    """GET a URL, parsed JSON. Tesserae's guarded fetch when it is there. Raises on a failure."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        from app.net_guard import fetch_json  # Tesserae's SSRF-guarded fetch
    except ImportError:
        fetch_json = None
    if fetch_json is not None:
        return fetch_json(url, headers=headers, timeout=TIMEOUT_S)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode("utf-8"))


def parse(body: Any) -> list[dict[str, str]]:
    """The dates in a service answer: [{"date": "2026-12-04", "type": "gft", "name": "GFT"}], sorted.
    The answer has this year (ophaaldagen) and, from late in the year, the next (ophaaldagenNext)."""
    out: list[dict[str, str]] = []
    if not isinstance(body, dict):
        return out
    for key in ("ophaaldagen", "ophaaldagenNext"):
        part = body.get(key)
        rows = part.get("data") if isinstance(part, dict) else None
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            day, kind = str(row.get("date") or "")[:10], str(row.get("type") or "").strip().lower()
            if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and kind):
                continue
            out.append({"date": day, "type": kind, "name": str(row.get("nameType") or kind).strip()})
    seen: set[tuple[str, str]] = set()
    unique = []
    for row in sorted(out, key=lambda r: (r["date"], r["type"])):
        if (row["date"], row["type"]) not in seen:
            seen.add((row["date"], row["type"]))
            unique.append(row)
    return unique


def fetch_all(a: dict[str, str], today: date) -> list[dict[str, str]]:
    query = {
        "apikey": a["api_key"],
        "method": "postcodecheck",
        "postcode": a["postcode"],
        "street": "",
        "huisnummer": a["huisnummer"],
        "toevoeging": a["toevoeging"],
        "app_name": "afvalwijzer",
        "platform": "phone",
        "afvaldata": today.isoformat(),
        "langs": "nl",
    }
    body = _get_json(f"{API_URL}?{urllib.parse.urlencode(query)}")
    rows = parse(body)
    if not rows:
        reason = ""
        if isinstance(body, dict):
            reason = str(body.get("error") or (body.get("ophaaldagen") or {}).get("error") or "")
        raise LookupError(reason or "no collection dates for this address")
    return rows


def _disk(data_dir: Path | None) -> Path | None:
    return data_dir / "pickups.json" if data_dir else None


def load(data_dir: Path | None = None, *, settings: dict[str, Any] | None = None, today: date | None = None, now: float | None = None) -> list[dict[str, str]]:
    """Every known collection date, from memory, disk or the service. A fresh answer is kept twelve hours;
    when the service fails, the last answer is used however old. Raises when there is neither."""
    a = address(settings)
    if not configured(settings):
        raise LookupError("not configured")
    now = time.time() if now is None else now
    today = today or date.today()
    key = f"{a['postcode']}|{a['huisnummer']}|{a['toevoeging']}"
    with _lock:
        hit = _memory.get(key)
    if hit and hit[0] > now:
        return hit[1]
    path = _disk(data_dir)
    stored: dict[str, Any] = {}
    if path is not None:
        with contextlib.suppress(OSError, ValueError):
            got = json.loads(path.read_text(encoding="utf-8"))
            stored = got if isinstance(got, dict) and got.get("key") == key else {}
    if stored and float(stored.get("at") or 0) + TTL_S > now:
        rows = list(stored.get("rows") or [])
        with _lock:
            _memory[key] = (float(stored["at"]) + TTL_S, rows)
        return rows
    try:
        rows = fetch_all(a, today)
    except Exception:  # noqa: BLE001 - the service is down: an old answer beats none
        if stored.get("rows"):
            return list(stored["rows"])
        raise
    with _lock:
        _memory[key] = (now + TTL_S, rows)
    if path is not None:
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"key": key, "at": now, "rows": rows}), encoding="utf-8")
    return rows


def pickups(
    start: date,
    end: date,
    *,
    data_dir: Path | None = None,
    types: list[str] | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """The collections from start up to and including end, optionally only of these types."""
    wanted = {t.strip().lower() for t in types or [] if t.strip()}
    lo, hi = start.isoformat(), end.isoformat()
    return [
        r for r in load(data_dir, settings=settings, today=start)
        if lo <= r["date"] <= hi and (not wanted or r["type"] in wanted)
    ]


def next_groups(rows: list[dict[str, str]], today: date, count: int) -> list[dict[str, Any]]:
    """The next collection days with what is collected on each: [{"date", "days", "items": [{"type", "name"}]}]."""
    groups: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        if r["date"] >= today.isoformat():
            groups.setdefault(r["date"], []).append({"type": r["type"], "name": r["name"]})
    out = []
    for day in sorted(groups)[: max(1, count)]:
        d = date.fromisoformat(day)
        out.append({"date": day, "days": (d - today).days, "weekday": d.weekday(), "items": groups[day]})
    return out


# ----------------------------------------------------------------------
# The plugin page: the address, and what the service says for it
# ----------------------------------------------------------------------
def save_address(store: Any, values: dict[str, Any]) -> None:
    """Store the address the way Tesserae's settings form does (secrets encrypted),
    the other settings left as they are."""
    keep = {k: str(values.get(k) or "").strip() for k in ("postcode", "huisnummer", "toevoeging") if k in values}
    fields = [f for f in _manifest_settings() if f["name"] in keep]
    store.update_for_namespace("plugins", PLUGIN_ID, keep, fields)


def blueprint() -> Any:
    from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

    bp = Blueprint("afvalwijzer_core_admin", __name__, template_folder="templates", root_path=str(_HERE))

    def preview() -> dict[str, Any]:
        out: dict[str, Any] = {"configured": configured(), "groups": [], "error": ""}
        if not out["configured"]:
            return out
        try:
            today = date.today()
            data_dir = Path(str(current_app.config["PLUGIN_REGISTRY"].get(PLUGIN_ID).data_dir))
            out["groups"] = next_groups(pickups(today, today + timedelta(days=120), data_dir=data_dir), today, 6)
        except Exception as err:  # noqa: BLE001 - shown on the page
            out["error"] = f"{type(err).__name__}: {err}"
        return out

    @bp.get("/")
    def index() -> Any:
        a = address()
        return render_template(
            "afvalwijzer_core/index.html",
            postcode=a["postcode"][:4] + " " + a["postcode"][4:] if a["postcode"] else "",
            huisnummer=a["huisnummer"],
            toevoeging=a["toevoeging"],
            **preview(),
        )

    @bp.post("/address")
    def set_address() -> Any:
        """Save the address. A form from the page, or the same fields as JSON."""
        body = request.get_json(silent=True)
        values = body if isinstance(body, dict) else request.form.to_dict()
        store = current_app.config.get("SETTINGS_STORE")
        if store is None or not hasattr(store, "update_for_namespace"):
            return jsonify({"ok": False, "error": "settings unavailable"}), 503
        save_address(store, values)
        _memory.clear()
        if isinstance(body, dict):
            return jsonify({"ok": True, "configured": configured()})
        flash("Address saved.", "success")
        return redirect(url_for("afvalwijzer_core_admin.index"))

    return bp
