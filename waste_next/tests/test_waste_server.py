"""waste_next: offline, with a fake Mijn Afvalwijzer plugin. The collections here are made up."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("waste_next_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]

core_spec = importlib.util.spec_from_file_location("afvalwijzer_core_server_w", HERE.parent / "afvalwijzer_core" / "server.py")
CORE = importlib.util.module_from_spec(core_spec)
core_spec.loader.exec_module(CORE)  # type: ignore[union-attr]

NOW = datetime(2026, 12, 1, 8, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
ROWS = [
    {"date": "2026-12-01", "type": "gft", "name": "GFT"},
    {"date": "2026-12-04", "type": "restafval", "name": "Restafval"},
    {"date": "2026-12-04", "type": "pmd", "name": "PMD"},
    {"date": "2026-12-09", "type": "papier", "name": "papier en karton"},
]


class FakeCore:
    def __init__(self, ok=True, fail=None):
        self.ok, self.fail, self.calls = ok, fail, []
        self.next_groups = CORE.next_groups

    def configured(self):
        return self.ok

    def pickups(self, start, end, *, data_dir=None, types=None):
        self.calls.append((start, end, types))
        if self.fail:
            raise self.fail
        wanted = {t.strip().lower() for t in types or []}
        return [r for r in ROWS if start.isoformat() <= r["date"] <= end.isoformat() and (not wanted or r["type"] in wanted)]


def run(opts=None, core=None, **kw):
    return S._fetch({"timezone": "Europe/Amsterdam", **(opts or {})}, {}, ctx={}, now=NOW, core=core or FakeCore(), **kw)


def test_the_tile_is_the_next_collection_and_today_counts() -> None:
    out = run()
    assert out["state"] == "ok" and out["display"] == "tile" and len(out["groups"]) == 1
    g = out["groups"][0]
    assert g["date"] == "2026-12-01" and g["days"] == 0 and g["items"] == [{"type": "gft", "name": "GFT"}]


def test_the_list_has_the_next_days_and_several_bins_on_one_day() -> None:
    out = run({"display": "list", "count": 3})
    assert [g["date"] for g in out["groups"]] == ["2026-12-01", "2026-12-04", "2026-12-09"]
    assert [i["type"] for i in out["groups"][1]["items"]] == ["restafval", "pmd"]


def test_only_the_types_asked_for() -> None:
    core = FakeCore()
    out = run({"types": "restafval; pmd"}, core=core)
    assert out["groups"][0]["date"] == "2026-12-04" and core.calls[0][2] == ["restafval", " pmd"]


def test_not_set_up_nothing_found_and_errors() -> None:
    assert run(core=FakeCore(ok=False))["state"] == "setup"
    assert run({"types": "glas"})["state"] == "empty"
    out = run(core=FakeCore(fail=LookupError("No Afvaldata")))
    assert out["state"] == "error" and "No Afvaldata" in out["error"]
    assert "Install the Mijn Afvalwijzer plugin" in S._fetch({}, {}, ctx={}, now=NOW, core=None)["error"]


def test_the_window_looks_ahead_and_language_strings_are_added() -> None:
    core = FakeCore()
    run(core=core)
    assert core.calls[0][1] - core.calls[0][0] == timedelta(days=S.HORIZON_DAYS)
    out = S.fetch({"language": "nl", "timezone": "Europe/Amsterdam"}, {}, ctx={}, now=NOW, core=FakeCore())
    assert out["lang"] == "nl" and out["strings"]["today"] == "Vandaag"
