"""weather_today: offline, from a canned Open-Meteo answer."""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("weather_today_server", HERE / "server.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # type: ignore[union-attr]


def raw(now_h: int = 14) -> dict:
    times = [f"2026-11-02T{h:02d}:00" for h in range(24)]
    return {
        "current": {"time": f"2026-11-02T{now_h:02d}:30", "temperature_2m": 12.6, "weather_code": 2, "is_day": 1},
        "hourly": {
            "time": times,
            "temperature_2m": [7 + (h % 7) for h in range(24)],
            "precipitation": [0.8 if 15 <= h <= 16 else 0 for h in range(24)],
            "precipitation_probability": [80 if 15 <= h <= 16 else 10 for h in range(24)],
            "weather_code": [80 if 15 <= h <= 16 else 3 for h in range(24)],
            "is_day": [1 if 8 <= h < 17 else 0 for h in range(24)],
        },
        "daily": {
            "time": ["2026-11-02"], "temperature_2m_max": [13.4], "temperature_2m_min": [6.6],
            "precipitation_sum": [1.6], "precipitation_probability_max": [80], "weather_code": [80],
        },
    }


def test_view() -> None:
    v = S.build_view(raw(), 7, "metric")
    assert v["date"] == "2026-11-02"
    assert v["now"] == {"t": 13, "cond": "showers", "icon": "showers"}  # a showery day leads with the showers
    assert (v["max"], v["min"], v["mm"]) == (13, 7, 1.6)
    hs = v["hours"]
    assert hs[0]["h"] == 7 and hs[-1]["h"] == 23 and len(hs) == 17
    assert [h["h"] for h in hs if h["now"]] == [14]
    assert all(h["past"] for h in hs if h["h"] < 14)
    assert next(h for h in hs if h["h"] == 15)["mm"] == 0.8
    assert next(h for h in hs if h["h"] == 20)["icon"] == "cloud"


def test_dry_day_leads_with_now() -> None:
    r = raw()
    r["daily"]["weather_code"] = [2]
    assert S.build_view(r, 7, "metric")["now"]["cond"] == "partly_cloudy"


def test_icons() -> None:
    assert S.icon("clear", True) == "sun" and S.icon("clear", False) == "moon"
    assert S.icon("partly_cloudy", False) == "moon_cloud"
    assert S.condition(None) == "cloudy" and S.condition(95) == "storm"


def test_needs_a_place() -> None:
    assert "error" in S.fetch({}, {}, ctx={"data_dir": "."})


def test_old_forecast_when_open_meteo_fails(tmp_path, monkeypatch) -> None:
    import json, os, time
    p = tmp_path / "today_52.267_4.970_metric.json"
    p.write_text(json.dumps(raw()), encoding="utf-8")
    old = time.time() - 3600
    os.utime(p, (old, old))

    def boom(url):
        raise OSError("down")

    monkeypatch.setattr(S, "_get_json", boom)
    v = S.fetch({"latitude": 52.2674, "longitude": 4.9704}, {}, ctx={"data_dir": str(tmp_path)})
    assert "error" not in v and v["max"] == 13
    os.utime(p, (old - 3 * 3600, old - 3 * 3600))
    assert "error" in S.fetch({"latitude": 52.2674, "longitude": 4.9704}, {}, ctx={"data_dir": str(tmp_path)})
