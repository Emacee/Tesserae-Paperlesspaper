"""energy_dynamic_price smoke test, upstream Tesserae pattern.

Needs the Tesserae checkout's conftest (the Flask ``client`` fixture) and
the dev ``/_test/render`` route, so it runs once the widget is installed
under ``plugins/energy_dynamic_price/``:

    .venv/bin/python -m pytest plugins/energy_dynamic_price/ -q
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

flask_testing = pytest.importorskip("flask.testing")


def _payload() -> bytes:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start -= timedelta(days=1)
    rows = [
        {"start": (start + timedelta(minutes=15 * k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "price": {"value": f"{0.30 + 0.05 * ((k // 4) % 5):.5f}"}}
        for k in range(96 * 3)
    ]
    return json.dumps({"all_in_with_vat": rows}).encode()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("size", ["xs", "sm", "md", "lg"])
def test_energy_dynamic_price_renders(client, size: str) -> None:
    from unittest.mock import patch

    with patch("urllib.request.urlopen", side_effect=lambda *a, **k: _Resp(_payload())):
        resp = client.get(f"/_test/render?plugin=energy_dynamic_price&size={size}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-plugin="energy_dynamic_price"' in body
    assert '"unit": "ct"' in body or '"unit":"ct"' in body
