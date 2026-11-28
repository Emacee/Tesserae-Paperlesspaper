"""waste_next: the next waste collection, from the Mijn Afvalwijzer plugin."""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HORIZON_DAYS = 120  # how far ahead to look for the next collection


def _plugin(name: str) -> Any:
    with contextlib.suppress(Exception):
        from flask import current_app

        return current_app.config["PLUGIN_REGISTRY"].get(name)
    return None


def _today(options: dict[str, Any], now: datetime | None):
    zone = timezone.utc
    with contextlib.suppress(Exception):
        from app.tz_resolve import app_timezone

        zone = app_timezone()
    name = str(options.get("timezone") or "")
    if name:
        with contextlib.suppress(Exception):
            from zoneinfo import ZoneInfo

            zone = ZoneInfo(name)
    return (now or datetime.now(timezone.utc)).astimezone(zone).date()


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


def _fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any], now: datetime | None = None, core: Any = None) -> dict[str, Any]:
    del settings
    core = core if core is not None else getattr(_plugin("afvalwijzer_core"), "server_module", None)
    display = "list" if str(options.get("display") or "tile") == "list" else "tile"
    title = " ".join(str(options.get("title") or "").split())
    if core is None:
        return {"state": "error", "error": "Install the Mijn Afvalwijzer plugin to use this widget.", "display": display, "title": title}
    if not core.configured():
        return {"state": "setup", "display": display, "title": title}
    today = _today(options, now)
    types = [t for t in str(options.get("types") or "").replace(";", ",").split(",") if t.strip()]
    data_dir = Path(str(ctx.get("data_dir"))) if ctx.get("data_dir") else None
    try:
        rows = core.pickups(today, today + timedelta(days=HORIZON_DAYS), data_dir=data_dir, types=types)
    except Exception as err:  # noqa: BLE001 - shown in the cell
        return {"state": "error", "error": f"{type(err).__name__}: {err}"[:160], "display": display, "title": title}
    try:
        count = max(1, min(8, int(options.get("count") or 4)))
    except (TypeError, ValueError):
        count = 4
    groups = core.next_groups(rows, today, count if display == "list" else 1)
    return {"state": "ok" if groups else "empty", "display": display, "title": title, "today": today.isoformat(), "groups": groups}


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any], **kw: Any) -> dict[str, Any]:
    data = _fetch(options, settings, ctx=ctx, **kw)
    lang, strings = strings_for(options)
    if lang and isinstance(data, dict):
        data["lang"], data["strings"] = lang, strings
    return data
