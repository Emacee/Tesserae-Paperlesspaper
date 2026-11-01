"""Build step: fetch this repository at a tag and copy its plugins and the
paperlesspaper device kind into the Tesserae image.

    python3 add_widgets.py <owner/repo> <ref>
"""

from __future__ import annotations

import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

PLUGINS = (
    "overhead_core",
    "overhead_photo",
    "overhead_plate",
    "overhead_cluster",
    "overhead_scene",
    "overhead_map",
    "energy_dynamic_price",
    "travel_time",
    "weather_today",
    "home_batteries",
    "paperlesspaper_core",
)
DEVICES = ("paperlesspaper",)
SKIP = shutil.ignore_patterns("tests", "screenshots", "__pycache__", "*.pyc", "out")


def main(repo: str, ref: str, app: Path = Path("/app")) -> None:
    url = f"https://github.com/{repo}/archive/{ref}.tar.gz"
    raw = urllib.request.urlopen(url, timeout=180).read()  # noqa: S310 - fixed https host
    src = Path("/tmp/widgets")  # noqa: S108 - build-time scratch
    shutil.rmtree(src, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        try:
            tar.extractall(src, filter="data")
        except TypeError:  # Python without extraction filters
            tar.extractall(src)  # noqa: S202 - our own repository's tarball
    root = next(src.iterdir())
    for name in PLUGINS:
        dst = app / "plugins" / name
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(root / name, dst, ignore=SKIP)
    for name in DEVICES:
        dst = app / "devices" / name
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(root / "devices" / name, dst, ignore=SKIP)
    shutil.rmtree(src)
    print(f"added {', '.join(PLUGINS)} and devices {', '.join(DEVICES)} from {url}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
