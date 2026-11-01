"""Overhead: Map, offline and without Tesserae: the feed, the lookups and the
map tiles are faked; the paintings fall back to photographs as on a server
without app.artwork, so this runs anywhere.

    python -m pytest overhead_core/tests/test_map.py -q
"""

from __future__ import annotations

import importlib.util
import io
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("overhead_map_server", ROOT / "overhead_map" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)  # type: ignore[union-attr]
SHEET = server._lib("sheet")
A, W, MAPS = SHEET.A, SHEET.W, SHEET.MAPS

HOME = (52.0, 5.0)


def ac(hexid: str, reg: str, typ: str, lat: float, lon: float, alt: int, gs: int, track: int = 270) -> dict:
    return {"hex": hexid, "r": reg, "t": typ, "lat": lat, "lon": lon, "alt_baro": alt, "gs": gs, "track": track, "flight": reg}


FEED = [
    ac("a1", "PH-AAA", "EC35", 52.02, 5.00, 900, 110),
    ac("a2", "PH-BBB", "C172", 51.97, 5.05, 1100, 95),
    ac("a3", "PH-CCC", "B738", 52.05, 4.95, 1400, 160),
    ac("a4", "PH-DDD", "R44", 51.99, 4.96, 600, 80),
    ac("a5", "PH-EEE", "DA40", 52.03, 5.06, 1300, 105),
    ac("a6", "PH-FFF", "EC45", 51.96, 4.97, 700, 120),
    ac("a7", "PH-GGG", "C152", 52.01, 4.93, 1000, 90),
    ac("a8", "PH-HHH", "B744", 52.00, 5.02, 9000, 300),  # above the ceiling
]


@pytest.fixture()
def faked(monkeypatch, tmp_path):
    feed = {"now": list(FEED)}

    def nearby(source, receiver_url, lat, lon, radius_km, data_dir, ua):
        return A._rows(feed["now"], lat, lon, radius_km), None, "adsb.lol"

    monkeypatch.setattr(A, "nearby", nearby)
    monkeypatch.setattr(A, "route_of", lambda *a, **k: {})
    monkeypatch.setattr(A, "photo_of", lambda *a, **k: {})
    monkeypatch.setattr(A, "owner_of", lambda *a, **k: "")
    monkeypatch.setattr(A, "type_photo", lambda *a, **k: {})
    tiles = []

    def tile(z, x, y, data_dir, ua):
        from PIL import Image

        tiles.append((z, x, y))
        out = io.BytesIO()
        Image.new("RGB", (256, 256), (200, 220, 200)).save(out, "PNG")
        return out.getvalue()

    monkeypatch.setattr(MAPS, "_tile", tile)
    yield {"feed": feed, "tiles": tiles, "dir": tmp_path}
    W.stop_watches()


OPTS = {"latitude": HOME[0], "longitude": HOME[1], "radius_km": "10", "max_alt_ft": "1500", "pictures": "photos"}


def run(faked, opts=None, w=860, h=880):
    return server.fetch(dict(OPTS, **(opts or {})), {}, ctx={"data_dir": str(faked["dir"]), "cell_w": w, "cell_h": h})


def test_at_most_six_and_the_rest_counted(faked) -> None:
    d = run(faked)
    assert d["state"] == "ok" and d["widget"] == "map"
    assert len(d["aircraft"]) == 6
    assert d["more"] == 1  # seven under the ceiling, the 747 above it is not counted
    assert all("lat" in a and a["track"] for a in d["aircraft"])
    assert d["home"] == [HOME[0], HOME[1]] and d["radius_km"] == 10
    assert d["map"]["src"].startswith("data:image/jpeg;base64,")
    assert d["credits"][0] == MAPS.ATTRIBUTION


def test_fewer_when_fewer_and_the_map_grows(faked) -> None:
    faked["feed"]["now"] = FEED[:2]
    d = run(faked)
    assert len(d["aircraft"]) == 2 and d["more"] == 0
    faked["feed"]["now"] = list(FEED)
    d6 = run(faked)
    assert d["map"]["h"] > d6["map"]["h"]  # one column of two lines leaves the map more room than three rows of two


def test_count_option_caps_at_six(faked) -> None:
    assert len(run(faked, {"count": 9})["aircraft"]) == 6
    assert len(run(faked, {"count": 3})["aircraft"]) == 3


def test_track_grows_between_renders(faked) -> None:
    run(faked)
    moved = [dict(a, lat=a["lat"] + 0.01, lon=a["lon"] - 0.01) for a in FEED]
    faked["feed"]["now"] = moved
    time.sleep(0.01)
    d = run(faked)
    first = d["aircraft"][0]
    assert len(first["track"]) >= 2
    lat, lon, alt, gs = first["track"][-1]
    assert isinstance(alt, int) and isinstance(gs, int)


def test_options_reach_the_page(faked) -> None:
    d = run(faked, {"track_colour": "speed", "track_minutes": "10", "show_radius": False, "map_style": "colour"})
    assert d["track_colour"] == "speed" and d["track_minutes"] == 10 and d["show_radius"] is False
    assert d["ceiling_ft"] == 1500


def test_empty_sky_still_has_the_map(faked) -> None:
    faked["feed"]["now"] = []
    d = run(faked)
    assert d["state"] == "empty" and d["map"] and d["home"]


def test_trail_points() -> None:
    e = {"trail": []}
    W.add_point(e, {"lat": 52.0, "lon": 5.0, "alt": 900, "gs": 100}, 1000)
    W.add_point(e, {"lat": 52.0001, "lon": 5.0, "alt": 950, "gs": 101}, 1060)  # 11 m: not a new point
    assert len(e["trail"]) == 1 and e["trail"][0][3] == 950
    W.add_point(e, {"lat": 52.01, "lon": 5.0, "alt": 1000, "gs": 102}, 1120)
    assert len(e["trail"]) == 2
    W.add_point(e, {"lat": 52.02, "lon": 5.0, "alt": 1000, "gs": 102}, 1120 + W.TRAIL_S + 10)
    assert len(e["trail"]) == 1  # the old end trimmed


def test_layout_matches_the_page() -> None:
    w1, h1 = MAPS.map_box(860, 880, 1)
    w6, h6 = MAPS.map_box(860, 880, 6, more=True)
    assert w1 == w6 and h1 > h6 > 120
    assert MAPS.list_rows(3) == (1, 3) and MAPS.list_rows(4) == (2, 2) and MAPS.list_rows(0) == (1, 0)


def test_fit_zoom() -> None:
    near = [(52.0, 5.0), (52.02, 5.03)]
    far = [(52.0, 5.0), (52.3, 5.5)]
    assert MAPS.fit_zoom(near, 800, 500) > MAPS.fit_zoom(far, 800, 500)
