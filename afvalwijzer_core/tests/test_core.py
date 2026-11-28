"""afvalwijzer_core: offline. The answers here are made up, in the shape of the service's."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("afvalwijzer_core_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]

SETTINGS = {"postcode_secret": "1234 ab", "huisnummer_secret": "12 ", "toevoeging": "A", "api_key": "KEY"}
ANSWER = {
    "ophaaldagen": {"response": "OK", "data": [
        {"nameType": "GFT", "type": "gft", "date": "2026-12-02"},
        {"nameType": "Restafval", "type": "restafval", "date": "2026-12-04"},
        {"nameType": "PMD", "type": "pmd", "date": "2026-12-04"},
        {"nameType": "papier en karton", "type": "papier", "date": "2026-12-09"},
        {"nameType": "GFT", "type": "gft", "date": "2026-12-02"},  # twice
        {"nameType": "?", "type": "", "date": "2026-12-10"},  # no type
    ], "error": False},
    "ophaaldagenNext": {"response": "OK", "data": [{"nameType": "GFT", "type": "gft", "date": "2027-01-06"}]},
}
TODAY = date(2026, 12, 1)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    S._memory.clear()
    asked: list[str] = []

    def get_json(url):
        asked.append(url)
        return ANSWER

    monkeypatch.setattr(S, "_get_json", get_json)
    return asked


def test_address_and_configured() -> None:
    a = S.address(SETTINGS)
    assert (a["postcode"], a["huisnummer"], a["toevoeging"]) == ("1234AB", "12", "A")
    assert S.configured(SETTINGS) and not S.configured({}) and not S.configured({**SETTINGS, "postcode_secret": "12"})


def test_parse_sorts_and_drops_duplicates_and_rows_without_type() -> None:
    rows = S.parse(ANSWER)
    assert [(r["date"], r["type"]) for r in rows] == [
        ("2026-12-02", "gft"), ("2026-12-04", "pmd"), ("2026-12-04", "restafval"), ("2026-12-09", "papier"), ("2027-01-06", "gft"),
    ]
    assert S.parse({"response": "NOK", "data": []}) == [] and S.parse(None) == []


def test_the_service_is_asked_with_the_address_and_kept_twelve_hours(clean, tmp_path) -> None:
    rows = S.load(tmp_path, settings=SETTINGS, today=TODAY, now=1000.0)
    assert len(rows) == 5 and len(clean) == 1
    assert "postcode=1234AB" in clean[0] and "huisnummer=12" in clean[0] and "toevoeging=A" in clean[0] and "apikey=KEY" in clean[0]
    S.load(tmp_path, settings=SETTINGS, today=TODAY, now=1000.0 + 3600)
    assert len(clean) == 1  # from memory
    S._memory.clear()
    S.load(tmp_path, settings=SETTINGS, today=TODAY, now=1000.0 + 3600)
    assert len(clean) == 1  # from disk
    S._memory.clear()
    S.load(tmp_path, settings=SETTINGS, today=TODAY, now=1000.0 + 13 * 3600)
    assert len(clean) == 2  # twelve hours later


def test_an_old_answer_is_used_when_the_service_fails(monkeypatch, tmp_path) -> None:
    S.load(tmp_path, settings=SETTINGS, today=TODAY, now=1000.0)
    S._memory.clear()

    def down(url):
        raise OSError("down")

    monkeypatch.setattr(S, "_get_json", down)
    assert len(S.load(tmp_path, settings=SETTINGS, today=TODAY, now=1000.0 + 99 * 3600)) == 5
    with pytest.raises(OSError):
        S.load(None, settings={**SETTINGS, "huisnummer_secret": "99"}, today=TODAY, now=1000.0)


def test_an_address_the_service_does_not_know_says_why(monkeypatch) -> None:
    monkeypatch.setattr(S, "_get_json", lambda url: {"response": "NOK", "data": [], "error": "No Afvaldata"})
    with pytest.raises(LookupError, match="No Afvaldata"):
        S.load(None, settings=SETTINGS, today=TODAY, now=1.0)
    with pytest.raises(LookupError, match="not configured"):
        S.load(None, settings={}, today=TODAY, now=1.0)


def test_pickups_window_types_and_next_groups() -> None:
    got = S.pickups(date(2026, 12, 1), date(2026, 12, 9), settings=SETTINGS)
    assert [r["date"] for r in got] == ["2026-12-02", "2026-12-04", "2026-12-04", "2026-12-09"]
    only = S.pickups(date(2026, 12, 1), date(2026, 12, 31), types=["GFT", " papier "], settings=SETTINGS)
    assert {r["type"] for r in only} == {"gft", "papier"}
    groups = S.next_groups(S.parse(ANSWER), TODAY, 2)
    assert [g["date"] for g in groups] == ["2026-12-02", "2026-12-04"]
    assert groups[0]["days"] == 1 and [i["type"] for i in groups[1]["items"]] == ["pmd", "restafval"]
    assert S.next_groups(S.parse(ANSWER), date(2026, 12, 4), 1)[0]["days"] == 0  # today counts
