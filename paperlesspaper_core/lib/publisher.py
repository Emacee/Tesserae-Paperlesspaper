"""Upload each new Tesserae frame of a ``paperlesspaper`` device to its paper.

Registered as a PushManager listener (``app/push.py``), the same way
Tesserae's own OpenDisplay-via-HA publisher is: on every push it looks at
the ``paperlesspaper`` devices, and for each whose composition changed reads
``<renders>/<digest>.png`` and posts it to the device's paper with
``POST /papers/uploadSingleImage/{paper}``. paperlesspaper dithers it and the
frame fetches it at its next wake-up.

Uploads run on one background worker, coalesced by a dirty flag, so a slow
upload never holds up the render pipeline. The page's Link and Upload now
buttons start theirs in the background too (``start``) and answer at once;
a device has one upload at a time, and taps while one runs fold into a single
follow-up. What was sent last is kept in a small JSON file, so a restart does
not upload the same frame again; the plugin page reads the same file for each
device's last upload.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KIND = "paperlesspaper"
ATTEMPTS = 3
RETRY_WAIT_S = 5.0  # before the second attempt; four times as long before the third
LANDED_SLACK_S = 5.0  # clock difference allowed when asking whether an upload landed
BUSY_NOTE = "An upload is already running; one more follows right after it."


def _epoch(value: Any) -> float | None:
    """A paperlesspaper timestamp (ISO text, or seconds or milliseconds) as seconds."""
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 1e11 else float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


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
        self._busy: set[str] = set()
        self._again: dict[str, bool] = {}  # device -> force, asked while its upload ran
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

    def is_busy(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._busy

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
        ``force``), and wait for it. (sent, a sentence for the page)."""
        plan, msg = self._plan(device_id, force)
        if plan is None:
            return False, msg
        return self._deliver(device_id, plan)

    def start(self, device_id: str, *, force: bool = True) -> tuple[bool, str]:
        """For a button: check what can be checked now, then upload in the
        background and answer at once. (started, a sentence for the page)."""
        plan, msg = self._plan(device_id, force)
        if plan is None:
            return False, msg
        if not self._run_async:
            return self._deliver(device_id, plan)
        try:
            threading.Thread(target=self._deliver, args=(device_id, plan), name="paperlesspaper-upload-now", daemon=True).start()
        except Exception:  # noqa: BLE001 - no thread to run it: free the device again
            with self._lock:
                self._busy.discard(device_id)
            raise
        return True, "Uploading now: the result shows under Last upload in a moment."

    def _plan(self, device_id: str, force: bool) -> tuple[dict[str, Any] | None, str]:
        """What to upload, with the device marked busy; or (None, why not)."""
        latest = self._latest(device_id) or {}
        digest = str(latest.get("composition_digest") or "")
        if not digest:
            return None, "Nothing rendered for this device yet: give it a page and send it once."
        cfg = self.config(device_id)
        paper = str(cfg.get("paper_id") or "").strip()
        if not paper:
            return None, "No paper set for this device: pick one on this page or under Settings › Devices."
        with self._lock:
            if device_id in self._busy:
                self._again[device_id] = self._again.get(device_id, False) or force
                return None, BUSY_NOTE
            last = self._state.get(device_id) or {}
            if not force and last.get("ok") and last.get("digest") == digest and last.get("paper") == paper:
                return None, "The latest frame is already on the paper."
            src = self._renders_dir / f"{digest}.png"
            try:
                png = src.read_bytes()
            except OSError:
                return None, f"The rendered frame {digest} is no longer on disk; render the page again."
            self._busy.add(device_id)
        orientation = str(cfg.get("orientation") or "landscape")
        settings = {"orientation": orientation if orientation in ("landscape", "portrait") else "landscape"}
        return {"digest": digest, "paper": paper, "png": png, "settings": settings}, ""

    def _deliver(self, device_id: str, plan: dict[str, Any]) -> tuple[bool, str]:
        started = time.monotonic()
        paper, digest = plan["paper"], plan["digest"]
        try:
            error, note = self._upload(paper, plan["png"], plan["settings"])
            ok = not error
            with self._lock:
                self._state[device_id] = {"digest": digest, "paper": paper, "at": int(time.time()), "ok": ok, "error": error}
                self._save()
            self._record(device_id, digest, ok, error, time.monotonic() - started, paper)
        finally:
            with self._lock:
                self._busy.discard(device_id)
                follow = self._again.pop(device_id, None)
        if ok:
            logger.info("paperlesspaper %s: uploaded frame %s to paper %s%s", device_id, digest, paper, f" ({note})" if note else "")
        else:
            logger.warning("paperlesspaper %s: upload to paper %s failed: %s", device_id, paper, error)
        if follow is not None:
            with contextlib.suppress(Exception):
                self.start(device_id, force=follow)
        if ok:
            return True, note or "Uploaded. The frame shows it at its next wake-up, or now if you press its button."
        return False, f"Upload failed: {error}"

    def _upload(self, paper: str, png: bytes, settings: dict[str, Any]) -> tuple[str, str]:
        """Up to ATTEMPTS tries. (error, note): error is empty when the image
        is on the paper; a slow answer that did land counts as sent."""
        waits = (self._retry_wait_s, self._retry_wait_s * 4)
        error = ""
        for attempt in range(ATTEMPTS):
            began = time.time()
            try:
                self._client().upload(paper, png, settings)
                return "", ""
            except Exception as err:  # noqa: BLE001 - ApiError, or anything the client raised
                error = str(err) or err.__class__.__name__
                if not getattr(err, "retryable", False):
                    return error, ""
                if self._landed(paper, began):
                    return "", "paperlesspaper was slow to answer, but the image is there"
                if attempt + 1 < ATTEMPTS:
                    time.sleep(waits[min(attempt, len(waits) - 1)])
        return error, ""

    def _landed(self, paper: str, since: float) -> bool:
        """Did the paper's image change after ``since``? A server that is slow
        to answer may still have taken the upload."""
        try:
            row = self._client().paper(paper)
        except Exception:  # noqa: BLE001 - cannot tell: treat as not landed
            return False
        at = _epoch((row or {}).get("imageUpdatedAt")) if isinstance(row, dict) else None
        return at is not None and at >= since - LANDED_SLACK_S

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
