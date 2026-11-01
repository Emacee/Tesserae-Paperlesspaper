"""A small client for the paperlesspaper API (https://docs.paperlesspaper.de).

Only the calls the plugin needs: upload an image to a paper, and read the
account's organisations, devices, papers and a device's events. Standard
library only (urllib + a hand-built multipart body), so the plugin has no
dependencies beyond what Tesserae ships.

Every call raises :class:`ApiError` with a sentence on failure; ``auth`` is
set when the key was refused (401/403), which is not worth retrying.
"""

from __future__ import annotations

import json
import secrets
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE = "https://api.paperlesspaper.de/v1"
USER_AGENT = "tesserae-paperlesspaper/0.1"
TIMEOUT_S = 60.0


class ApiError(Exception):
    def __init__(self, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.status = status

    @property
    def auth(self) -> bool:
        return self.status in (401, 403)

    @property
    def retryable(self) -> bool:
        """A network failure, a timeout, a rate limit or a server error."""
        return self.status == 0 or self.status == 429 or self.status >= 500


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    """(body, content type) for a multipart/form-data request. ``files`` maps
    a field to (filename, bytes, mime)."""
    boundary = "tesserae-" + secrets.token_hex(12)
    out = bytearray()
    for name, value in fields.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += value.encode("utf-8") + b"\r\n"
    for name, (filename, raw, mime) in files.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        out += f"Content-Type: {mime}\r\n\r\n".encode()
        out += raw + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


class Client:
    def __init__(self, api_key: str, base: str = DEFAULT_BASE, timeout: float = TIMEOUT_S) -> None:
        self.key = (api_key or "").strip()
        self.base = (base or DEFAULT_BASE).strip().rstrip("/")
        self.timeout = timeout

    # -- plumbing ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str = "",
    ) -> Any:
        if not self.key:
            raise ApiError("No paperlesspaper API key: add one on the paperlesspaper page (Settings > Widgets > paperlesspaper > Open admin).", status=401)
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, "")})
        headers = {"x-api-key": self.key, "Accept": "application/json", "User-Agent": USER_AGENT}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - fixed https base
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = ""
            try:
                detail = err.read().decode("utf-8", "replace").strip()[:300]
            except Exception:  # noqa: BLE001
                detail = ""
            why = {401: "refused the API key", 403: "does not allow this for the API key", 404: "does not know it", 429: "asks to slow down"}.get(
                err.code, f"answered HTTP {err.code}"
            )
            raise ApiError(f"paperlesspaper {why}" + (f": {detail}" if detail else "") + ".", status=err.code) from err
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as err:
            reason = getattr(err, "reason", err)
            raise ApiError(f"paperlesspaper could not be reached ({reason}).") from err
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw.decode("utf-8", "replace")

    # -- calls -------------------------------------------------------------

    def upload(self, paper_id: str, png: bytes, settings: dict[str, Any] | None = None) -> Any:
        """Replace a paper's image: ``picture`` is the full-colour frame;
        paperlesspaper prepares (dithers) it for the device. ``settings`` is
        merged into the paper's meta first (orientation, lut)."""
        paper_id = (paper_id or "").strip()
        if not paper_id:
            raise ApiError("No paper set for this device.")
        fields = {"settings": json.dumps(settings)} if settings else {}
        body, ctype = multipart(fields, {"picture": ("tesserae.png", png, "image/png")})
        return self._request(
            "POST", f"/papers/uploadSingleImage/{urllib.parse.quote(paper_id, safe='')}", body=body, content_type=ctype
        )

    def organizations(self) -> list[dict[str, Any]]:
        return _items(self._request("GET", "/organizations/"))

    def devices(self, organization: str) -> list[dict[str, Any]]:
        return _items(self._request("GET", "/devices/", query={"organization": organization}))

    def device(self, device_id: str) -> dict[str, Any]:
        got = self._request("GET", f"/devices/{urllib.parse.quote(device_id, safe='')}")
        return got if isinstance(got, dict) else {}

    def papers(self, *, device: str = "", organization: str = "") -> list[dict[str, Any]]:
        """The papers (screens) of a device, or of an organisation when no
        device is given."""
        return _items(
            self._request("GET", "/papers/", query={"deviceId": device, "organization": organization, "limit": 100})
        )

    def paper(self, paper_id: str) -> dict[str, Any]:
        got = self._request("GET", f"/papers/{urllib.parse.quote(paper_id, safe='')}")
        return got if isinstance(got, dict) else {}

    def show_paper(self, device_id: str, paper_id: str) -> Any:
        """Make ``paper_id`` the paper the frame shows from its next wake-up."""
        body = json.dumps({"paper": paper_id}).encode()
        return self._request(
            "PATCH", f"/devices/{urllib.parse.quote(device_id, safe='')}", body=body, content_type="application/json"
        )

    def events(self, device_id: str) -> list[dict[str, Any]]:
        return _items(self._request("GET", f"/devices/events/{urllib.parse.quote(device_id, safe='')}"))


def _items(got: Any) -> list[dict[str, Any]]:
    """The rows of a list answer, whatever it is wrapped in (a bare list, or
    a page with results / docs / data / items)."""
    if isinstance(got, list):
        return [x for x in got if isinstance(x, dict)]
    if isinstance(got, dict):
        for key in ("results", "docs", "data", "items"):
            if isinstance(got.get(key), list):
                return [x for x in got[key] if isinstance(x, dict)]
    return []


def ident(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("_id") or "")


def label(row: dict[str, Any]) -> str:
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    manifest = meta.get("pluginManifest") if isinstance(meta.get("pluginManifest"), dict) else {}
    for value in (
        row.get("name"),
        row.get("title"),
        meta.get("name"),
        manifest.get("name"),
        row.get("deviceId"),
        row.get("serialNumber"),
    ):
        if value:
            return str(value)
    return ident(row)


def ref(value: Any) -> str:
    """An id from a field that may hold the id or the populated object."""
    if isinstance(value, dict):
        return ident(value)
    return str(value or "")
