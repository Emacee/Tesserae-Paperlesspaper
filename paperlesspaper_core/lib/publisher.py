"""Upload each new Tesserae frame of a ``paperlesspaper`` device to its paper.

Registered as a PushManager listener (``app/push.py``), the same way
Tesserae's own OpenDisplay-via-HA publisher is: on every push it looks at
the ``paperlesspaper`` devices, and for each whose composition changed reads
``<renders>/<digest>.png`` and posts it to the device's paper with
``POST /papers/uploadSingleImage/{paper}``. paperlesspaper dithers it and the
frame fetches it at its next wake-up.

Uploads run on one background worker, coalesced by a dirty flag, so a slow
upload never holds up the render pipeline. What was sent last is kept in a
small JSON file, so a restart does not upload the same frame again; the
plugin page reads the same file for each device's last upload.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KIND = "paperlesspaper"
RETRY_WAIT_S = 5.0


class Uploader:
    def __init__(
        self,
        *,
        devices: Any,
        settings: Any,
        renders_dir: Path,
        latest_render_fn: Callable[[str], dict[str, Any] | None],
        client_fn: Callable[[], Any],
        state_path: Path,
        event_log: Any = None,
        run_async: bool = True,
        retry_wait_s: float = RETRY_WAIT_S,
    ) -> None:
        self._devices = devices
        self._settings = settings
        self._renders_dir = Path(renders_dir)
        self._latest = latest_render_fn
        self._client = client_fn
        self._state_path = Path(state_path)
        self._events = event_log
        self._run_async = run_async
        self._retry_wait_s = retry_wait_s
        self._lock = threading.Lock()
        self._dirty = False
        self._worker_running = False
        self._state = self._load()

    # -- state -------------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        with contextlib.suppress(OSError, ValueError):
            got = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(got, dict):
                return {k: v for k, v in got.items() if isinstance(v, dict)}
        return {}

    def _save(self) -> None:
        with contextlib.suppress(OSError):
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_name(self._state_path.name + ".tmp")
            tmp.write_text(json.dumps(self._state, indent=1), encoding="utf-8")
            tmp.replace(self._state_path)

    def status(self, device_id: str) -> dict[str, Any]:
        """The device's last upload: {digest, paper, at, ok, error}."""
        with self._lock:
            return dict(self._state.get(device_id) or {})

    # -- devices -----------------------------------------------------------

    def devices(self) -> list[Any]:
        return [d for d in self._devices.devices.values() if getattr(d, "kind_of", None) == KIND]

    def config(self, device_id: str) -> dict[str, Any]:
        section = self._settings.get_section("devices") or {}
        cfg = section.get(device_id) if isinstance(section, dict) else None
        return cfg if isinstance(cfg, dict) else {}

    # -- push reaction -----------------------------------------------------

    def on_push(self, _result: Any = None) -> None:
        """Listener entry point, in the push thread: never raises, never blocks."""
        try:
            if not self.devices():
                return
            if not self._run_async:
                self.process_once()
                return
            with self._lock:
                self._dirty = True
                if self._worker_running:
                    return
                self._worker_running = True
            threading.Thread(target=self._worker, name="paperlesspaper-upload", daemon=True).start()
        except Exception:  # noqa: BLE001 - a listener must not break the pipeline
            logger.exception("paperlesspaper: on_push failed")

    def _worker(self) -> None:
        while True:
            with self._lock:
                if not self._dirty:
                    self._worker_running = False
                    return
                self._dirty = False
            self.process_once()

    def process_once(self) -> None:
        for device in self.devices():
            try:
                self.send(device.id)
            except Exception:  # noqa: BLE001
                logger.exception("paperlesspaper: upload failed for %s", device.id)

    # -- one device --------------------------------------------------------

    def send(self, device_id: str, *, force: bool = False) -> tuple[bool, str]:
        """Upload the device's latest frame when it changed (or always, with
        ``force``). (sent, a sentence for the page)."""
        latest = self._latest(device_id) or {}
        digest = str(latest.get("composition_digest") or "")
        if not digest:
            return False, "Nothing rendered for this device yet: give it a page and send it once."
        cfg = self.config(device_id)
        paper = str(cfg.get("paper_id") or "").strip()
        if not paper:
            return False, "No paper set for this device: pick one on this page or under Settings › Devices."
        with self._lock:
            last = self._state.get(device_id) or {}
            if not force and last.get("ok") and last.get("digest") == digest and last.get("paper") == paper:
                return False, "The latest frame is already on the paper."
        src = self._renders_dir / f"{digest}.png"
        try:
            png = src.read_bytes()
        except OSError:
            return False, f"The rendered frame {digest} is no longer on disk; render the page again."
        orientation = str(cfg.get("orientation") or "landscape")
        settings = {"orientation": orientation if orientation in ("landscape", "portrait") else "landscape"}
        started = time.monotonic()
        error = ""
        for attempt in range(2):
            try:
                self._client().upload(paper, png, settings)
                error = ""
                break
            except Exception as err:  # noqa: BLE001 - ApiError, or anything the client raised
                error = str(err) or err.__class__.__name__
                if attempt == 0 and getattr(err, "retryable", False):
                    time.sleep(self._retry_wait_s)
                    continue
                break
        ok = not error
        with self._lock:
            self._state[device_id] = {
                "digest": digest,
                "paper": paper,
                "at": int(time.time()),
                "ok": ok,
                "error": error,
            }
            self._save()
        self._record(device_id, digest, ok, error, time.monotonic() - started, paper)
        if ok:
            logger.info("paperlesspaper %s: uploaded frame %s to paper %s", device_id, digest, paper)
            return True, "Uploaded. The frame shows it at its next wake-up, or now if you press its button."
        logger.warning("paperlesspaper %s: upload to paper %s failed: %s", device_id, paper, error)
        return False, f"Upload failed: {error}"

    def _record(self, device_id: str, digest: str, ok: bool, error: str, took: float, paper: str) -> None:
        if self._events is None:
            return
        with contextlib.suppress(Exception):
            self._events.record(
                type="paperlesspaper",
                source="paperlesspaper_core",
                target=device_id,
                status="ok" if ok else "failed",
                digest=digest or None,
                error=error or None,
                duration_s=took,
                extra={"paper": paper},
            )
