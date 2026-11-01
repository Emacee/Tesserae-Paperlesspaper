"""The map under Overhead: Map. OpenStreetMap tiles around the place,
stitched to the size of the map on the page and quietened for e-paper
(most of the colour out, a little lighter), with the place, the radius and
each aircraft's track drawn over it by the page.

Tiles come from tile.openstreetmap.org with the contact from Overhead
Core's settings in the User-Agent, as its tile usage policy asks, and are
kept on disk for a month (a page around one place asks for the same few
tiles every time). The map credits OpenStreetMap's contributors.
Loaded by path."""

from __future__ import annotations

import base64
import contextlib
import io
import math
import time
import urllib.request
from pathlib import Path
from typing import Any

TILE = 256
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_KEEP_S = 30 * 86400
TILE_TIMEOUT_S = 6
MAX_TILES = 48  # one map never asks for more than this many
ATTRIBUTION = "© OpenStreetMap-bijdragers"
MAP_STYLES = ("grey", "colour")


def world(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Web Mercator pixel coordinates at zoom ``z``."""
    n = TILE * 2**z
    lat = max(-85.0, min(85.0, lat))
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def metres_per_px(lat: float, z: int) -> float:
    return 156_543.03392 * math.cos(math.radians(lat)) / 2**z


def fit_zoom(points: list[tuple[float, float]], w: int, h: int, *, pad: float = 0.8, zmin: int = 8, zmax: int = 14) -> int:
    """The closest zoom at which every point fits in ``pad`` of a w x h map."""
    for z in range(zmax, zmin - 1, -1):
        xs, ys = zip(*(world(a, b, z) for a, b in points))
        if max(xs) - min(xs) <= w * pad and max(ys) - min(ys) <= h * pad:
            return z
    return zmin


def _tile(z: int, x: int, y: int, data_dir: Path, ua: str) -> bytes | None:
    n = 2**z
    if not (0 <= y < n):
        return None
    x %= n
    path = data_dir / "tiles" / str(z) / str(x) / f"{y}.png"
    with contextlib.suppress(OSError):
        if time.time() - path.stat().st_mtime < TILE_KEEP_S:
            return path.read_bytes()
    try:
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=TILE_TIMEOUT_S) as resp:  # noqa: S310 - fixed https host
            raw = resp.read()
    except Exception:  # noqa: BLE001 - an old tile, or a blank square
        with contextlib.suppress(OSError):
            return path.read_bytes()
        return None
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return raw


def render(
    center: tuple[float, float], z: int, w: int, h: int, data_dir: Path, ua: str, style: str = "grey"
) -> dict[str, Any] | None:
    """A w x h map centred on ``center`` at zoom ``z``: the image as a data
    URI, with what the page needs to put points on it (the world pixel of
    its top-left corner at that zoom)."""
    from PIL import Image, ImageEnhance

    w, h = max(64, int(w)), max(64, int(h))
    cx, cy = world(center[0], center[1], z)
    x0, y0 = cx - w / 2, cy - h / 2
    tx0, ty0 = int(x0 // TILE), int(y0 // TILE)
    tx1, ty1 = int((x0 + w) // TILE), int((y0 + h) // TILE)
    if (tx1 - tx0 + 1) * (ty1 - ty0 + 1) > MAX_TILES:
        return None
    img = Image.new("RGB", (w, h), (236, 234, 228))
    got = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            raw = _tile(z, tx, ty, data_dir, ua)
            if not raw:
                continue
            with contextlib.suppress(Exception):
                with Image.open(io.BytesIO(raw)) as t:
                    img.paste(t.convert("RGB"), (int(tx * TILE - x0), int(ty * TILE - y0)))
                    got += 1
    if not got:
        return None
    if style == "grey":
        img = ImageEnhance.Color(img).enhance(0.35)
        img = ImageEnhance.Brightness(img).enhance(1.06)
        img = ImageEnhance.Contrast(img).enhance(0.9)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True)
    return {
        "src": "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode(),
        "z": z,
        "x0": round(x0, 2),
        "y0": round(y0, 2),
        "w": w,
        "h": h,
        "mpp": round(metres_per_px(center[0], z), 3),
        "credit": ATTRIBUTION,
    }


# ----------------------------------------------------------------------
# The page's layout, shared with overhead.js: the list under the map takes
# one column up to three aircraft and two from four, and the map the rest.
# ----------------------------------------------------------------------
HEAD_PX = 92  # the title and its rule, at a 1600 px tall panel's scale
GAP_PX = 18


def list_rows(n: int) -> tuple[int, int]:
    """(columns, rows) of the list for n aircraft."""
    cols = 1 if n <= 3 else 2
    return cols, (math.ceil(n / cols) if n else 0)


def map_box(cell_w: int, cell_h: int, n: int, *, more: bool = False) -> tuple[int, int]:
    """The map's size in a cell of cell_w x cell_h showing n aircraft."""
    s = scale(cell_w, cell_h)
    cols, rows = list_rows(n)
    row_h = (86 if cols == 1 else 78) * s
    list_h = rows * row_h + (28 * s if more else 0)
    w = cell_w - 8 * s
    h = cell_h - HEAD_PX * s - list_h - (GAP_PX * s if n else 0)
    return int(w), int(max(120, h))


def scale(cell_w: int, cell_h: int) -> float:
    """Type and spacing scale with the cell: 1 at about 860 px wide."""
    return max(0.55, min(1.4, min(cell_w / 860, cell_h / 880 * 1.2)))
