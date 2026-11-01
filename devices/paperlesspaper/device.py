"""paperlesspaper device contract.

A paperlesspaper frame on its stock firmware. It never talks to Tesserae: it
wakes on its own schedule and fetches the image stored on its paper in the
paperlesspaper cloud. Tesserae renders a full-colour PNG for this push-only
device, and the ``paperlesspaper_core`` plugin uploads it to the paper named
in ``paper_id``; paperlesspaper dithers it for the panel.

Heartbeats never arrive (the frame reports to paperlesspaper, not here); the
plugin page reads its battery and wake times from the paperlesspaper API.
"""

from __future__ import annotations

import json
import re
from typing import Any

_ORIENTATIONS = {"landscape", "portrait"}
# paperlesspaper ids are Mongo-style object ids (24 hex), but accept any
# plain token so a future id format still saves
_PAPER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def parse_status(payload: bytes) -> dict[str, Any]:
    """Decode a heartbeat JSON blob; return ``{"raw": …}`` on non-JSON."""
    if not payload:
        return {"raw": ""}
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw": payload.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"raw": decoded}


def validate_config(payload: dict[str, Any]) -> tuple[bool, str | None]:
    """An optional paper id and an orientation. Both may be left empty so a
    half-configured device still saves (the uploader skips a device with no
    paper)."""
    paper = payload.get("paper_id")
    if paper is not None:
        if not isinstance(paper, str):
            return False, "paper_id must be a string"
        if paper.strip() and not _PAPER_ID.fullmatch(paper.strip()):
            return False, "paper_id is the paper's id, letters and digits only"
    orientation = payload.get("orientation")
    if orientation is not None and str(orientation) not in _ORIENTATIONS:
        return False, "orientation must be landscape or portrait"
    return True, None
