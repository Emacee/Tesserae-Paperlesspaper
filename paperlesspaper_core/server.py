"""paperlesspaper Core: send Tesserae pages to paperlesspaper frames on their
stock firmware, and manage the frames' papers from Tesserae.

* An uploader hangs on Tesserae's push pipeline and posts each new frame of a
  ``paperlesspaper`` device (``devices/paperlesspaper``) to that device's
  paper in the paperlesspaper cloud.
* The plugin page (Settings > Widgets > paperlesspaper > Open admin) takes
  the API key and lists the frames on the
  account, their papers (the Tesserae paper beside paperlesspaper's own
  integrations), which paper each frame shows, its battery and last
  wake-up; it switches the paper a frame shows, links a paper to a Tesserae
  device, and uploads on demand.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for

_HERE = Path(__file__).resolve().parent
PLUGIN_ID = "paperlesspaper_core"
WATCH_S = 30  # how often the listener is checked to still hang on the push pipeline
PAGE_TIMEOUT_S = 15.0

logger = logging.getLogger(__name__)


def lib(name: str) -> Any:
    full = f"_tesserae_plugins.{PLUGIN_ID}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _HERE / "lib" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


API = lib("api")
PUB = lib("publisher")


# ----------------------------------------------------------------------
# settings and the client
# ----------------------------------------------------------------------
def settings_of(store: Any) -> dict[str, Any]:
    if store is None:
        return {}
    with contextlib.suppress(Exception):
        got = store.get_for_runtime("plugins", PLUGIN_ID, _manifest_settings())
        return got if isinstance(got, dict) else {}
    return {}


def _manifest_settings() -> list[dict[str, Any]]:
    try:
        manifest = json.loads((_HERE / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    fields = manifest.get("settings", []) if isinstance(manifest, dict) else []
    return [f for f in fields if isinstance(f, dict) and f.get("name")]


def settings_url() -> str:
    """Tesserae's own form for this plugin's settings: Settings > Widgets,
    the card of this plugin (``/settings/plugins#plugin-<id>``)."""
    anchor = f"plugin-{PLUGIN_ID}"
    try:
        return url_for("auth.settings_area", area="plugins", _anchor=anchor)
    except Exception:  # noqa: BLE001 - a host without that endpoint
        return f"{request.script_root}/settings/plugins#{anchor}"


def save_api_key(store: Any, key: str) -> None:
    """Store the key the way Tesserae's settings form does: encrypted, as
    ``api_key_secret``, the other settings left as they are."""
    fields = [f for f in _manifest_settings() if f["name"] == "api_key"]
    store.update_for_namespace("plugins", PLUGIN_ID, {"api_key": key}, fields)


def client_for(app: Any, timeout: float = API.TIMEOUT_S) -> Any:
    st = settings_of(app.config.get("SETTINGS_STORE"))
    return API.Client(str(st.get("api_key") or ""), str(st.get("api_base") or API.DEFAULT_BASE), timeout=timeout)


class _Live:
    """An app.config entry looked up at each use, so a registry or store the
    host rebuilds is never held stale."""

    def __init__(self, app: Any, key: str) -> None:
        self._app = app
        self._key = key

    def __getattr__(self, name: str) -> Any:
        target = self._app.config.get(self._key)
        if target is None:
            raise AttributeError(f"{self._key} is not ready")
        return getattr(target, name)


def _data_dir(app: Any) -> Path:
    registry = app.config.get("PLUGIN_REGISTRY")
    for pl in list(getattr(registry, "plugins", {}).values()) if registry is not None else []:
        with contextlib.suppress(OSError, AttributeError, TypeError):
            if Path(pl.path).resolve() == _HERE:
                path = Path(pl.data_dir)
                path.mkdir(parents=True, exist_ok=True)
                return path
    root = Path(app.config.get("DATA_ROOT") or "/tmp") / "plugins" / PLUGIN_ID  # noqa: S108 - last resort
    root.mkdir(parents=True, exist_ok=True)
    return root


def uploader(app: Any) -> Any:
    """The app's one uploader, built on first use."""
    up = app.config.get("PAPERLESSPAPER_UPLOADER")
    if up is None:
        up = PUB.Uploader(
            devices=_Live(app, "DEVICE_REGISTRY"),
            settings=_Live(app, "SETTINGS_STORE"),
            renders_dir=Path(app.config.get("RENDERS_DIR") or "."),
            latest_render_fn=lambda device_id: _latest(app, device_id),
            client_fn=lambda: client_for(app),
            state_path=_data_dir(app) / "sent.json",
            event_log=_Live(app, "EVENT_LOG"),
        )
        app.config["PAPERLESSPAPER_UPLOADER"] = up
    return up


def _latest(app: Any, device_id: str) -> dict[str, Any] | None:
    push = app.config.get("PUSH_MANAGER")
    return push.latest_render_for(device_id) if push is not None else None


def attach(app: Any) -> bool:
    """Hang the uploader on the push pipeline; True once it hangs there.
    Safe to call again: add_listener ignores a listener it already has."""
    push = app.config.get("PUSH_MANAGER")
    if push is None or app.config.get("RENDERS_DIR") is None or app.config.get("DEVICE_REGISTRY") is None:
        return False
    up = uploader(app)
    push.add_listener(up.on_push)
    return True


def _watch(app: Any) -> None:
    """The push manager can be rebuilt (a transport change) after the plugins
    load: keep the uploader on whichever one is current."""
    while True:
        with contextlib.suppress(Exception):
            attach(app)
        time.sleep(WATCH_S)


# ----------------------------------------------------------------------
# Home Assistant without a token to paste: inside the Home Assistant app,
# Supervisor hands the container a token for its own API proxy
# (``homeassistant_api: true`` in config.yaml). Home Assistant Core (the
# plugin every HA widget reads through) is pointed at it on every start,
# unless it was set to another Home Assistant by hand.
# ----------------------------------------------------------------------
SUPERVISOR_CORE = "http://supervisor/core"


def _ha_fields(app: Any) -> list[dict[str, Any]]:
    reg = app.config.get("PLUGIN_REGISTRY")
    plugin = reg.get("ha_core") if reg is not None else None
    manifest = getattr(plugin, "manifest", None) or {}
    return [f for f in manifest.get("settings") or [] if isinstance(f, dict) and f.get("name")]


def configure_ha(app: Any, env: dict[str, str] | None = None) -> str:
    """Point Home Assistant Core at Supervisor's proxy with the app's own
    token. Returns what was done: "set", "kept" (a URL of the user's own),
    "skipped" (not inside the Home Assistant app, or no ha_core)."""
    env = dict(os.environ) if env is None else env
    token = str(env.get("SUPERVISOR_TOKEN") or "").strip()
    store = app.config.get("SETTINGS_STORE")
    fields = _ha_fields(app)
    if not (env.get("TESSERAE_HA_INGRESS") and token) or store is None or not fields:
        return "skipped"
    try:
        current = store.get_for_runtime("plugins", "ha_core", fields) or {}
    except Exception:  # noqa: BLE001
        current = {}
    url = str(current.get("base_url") or "").strip().rstrip("/")
    if url and url != SUPERVISOR_CORE:
        return "kept"
    store.update_for_namespace(
        "plugins", "ha_core", {"base_url": SUPERVISOR_CORE, "token": token, "verify_tls": True}, fields
    )
    return "set"


def save_device_values(store: Any, device_id: str, values: dict[str, Any]) -> None:
    if hasattr(store, "update_item"):
        store.update_item("devices", device_id, values)
        return
    section = store.get_section("devices") or {}
    merged = {**dict(section.get(device_id) or {}), **values}
    store.patch_section("devices", {device_id: merged})


DEVICE_ID = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


def setup_device(app: Any, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Create a device of the paperlesspaper kind, as Settings > Devices >
    Add device does, with its orientation and (optionally) its paper."""
    from app import device_service, renderer_loader

    device_id = str(body.get("id") or "").strip()
    if not DEVICE_ID.match(device_id):
        return 400, {"error": "id: 2-32 chars, a lowercase letter first, then letters, digits, _ or -"}
    orientation = "portrait" if str(body.get("orientation") or "") == "portrait" else "landscape"
    devices = app.config["DEVICE_REGISTRY"]
    store = app.config["SETTINGS_STORE"]
    existing = devices.get(device_id) if hasattr(devices, "get") else None
    if existing is None:
        result = device_service.create_instance(
            devices=devices,
            renderers=app.config["RENDERER_REGISTRY"],
            data_root=app.config["DEVICE_DATA_ROOT"],
            instance_id=device_id,
            kind_id="paperlesspaper",
            name=str(body.get("name") or device_id),
            orientation=orientation,
        )
        if not result.ok or result.device is None:
            return 400, {"error": result.error or "the device could not be added"}
        device = result.device
        created = True
    else:
        device = existing
        created = False
    values = {"orientation": orientation}
    if body.get("paper_id"):
        values["paper_id"] = str(body["paper_id"]).strip()
    try:
        from app.settings._shared import config_fields_from_schema

        schema_fields = [f for f in config_fields_from_schema(device.config_schema) if f["name"] in values]
    except Exception:  # noqa: BLE001 - an older Tesserae: the fields as the schema has them
        schema_fields = [{"name": k, **v} for k, v in (device.config_schema or {}).items() if k in values and isinstance(v, dict)]
    problem = None
    if schema_fields and hasattr(device_service, "save_device_config"):
        problem = device_service.save_device_config(store, devices, device, values, schema_fields)
    else:  # Tesserae before save_device_config: the device's settings as the link form saves them
        save_device_values(store, device.id, values)
    if created and hasattr(device_service, "device_added"):
        device_service.device_added(store, device)
    if created:
        with contextlib.suppress(Exception):
            renderer_loader.seed_device_settings_from_base(app.config["RENDERER_REGISTRY"], store)
    with contextlib.suppress(Exception):
        app.config["REBUILD_TRANSPORT"]()
    return 200, {"id": device.id, "created": created, "orientation": orientation, "config_problem": problem}


def _start(state: Any) -> None:
    app = state.app
    with contextlib.suppress(Exception):
        logger.info("paperlesspaper: Home Assistant Core %s", configure_ha(app))
    if app.config.get("PAPERLESSPAPER_WATCH"):
        attach(app)
        return
    app.config["PAPERLESSPAPER_WATCH"] = True
    attach(app)
    threading.Thread(target=_watch, args=(app,), name="paperlesspaper-watch", daemon=True).start()


# ----------------------------------------------------------------------
# the page
# ----------------------------------------------------------------------
def _when(value: Any) -> str:
    if not value:
        return ""
    with contextlib.suppress(TypeError, ValueError, OSError):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value)).strftime("%d-%m %H:%M")
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%d-%m %H:%M")
    return str(value)


def _decoded(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in "{[":
        with contextlib.suppress(ValueError):
            return json.loads(value)
    return value


def _find_wake(value: Any, depth: int = 0) -> dict[str, Any] | None:
    """The frame's own report ({"bat", "wake", "fw", …}), wherever the event
    nests it (payload, payload.json, a JSON string)."""
    value = _decoded(value)
    if isinstance(value, dict):
        if "bat" in value or "wake" in value:
            return value
        if depth < 3:
            for inner in value.values():
                got = _find_wake(inner, depth + 1)
                if got:
                    return got
    return None


def _find_state(value: Any, depth: int = 0) -> str:
    value = _decoded(value)
    if isinstance(value, str):
        return value if value.startswith(("update_", "download_")) else ""
    if isinstance(value, dict) and depth < 3:
        for inner in value.values():
            got = _find_state(inner, depth + 1)
            if got:
                return got
    return ""


def wake_info(events: list[dict[str, Any]]) -> dict[str, Any]:
    """From a device's events (``{type, payload, timestamp}``): the last
    wake-up with battery and what woke it, and the last update result."""
    out: dict[str, Any] = {}
    rows = sorted(events, key=lambda e: str(e.get("timestamp") or e.get("createdAt") or ""), reverse=True)
    for e in rows:
        kind = str(e.get("type") or e.get("eventType") or "")
        body = {k: v for k, v in e.items() if k not in ("id", "deviceId", "type", "timestamp", "createdAt")}
        at = _when(e.get("timestamp") or e.get("createdAt"))
        if "wake" not in out and kind != "state":
            data = _find_wake(body)
            if data:
                bat = str(data.get("bat") or "")
                out["wake"] = {
                    "at": at,
                    "why": str(data.get("wake") or "").lower(),
                    "battery": f"{int(bat) / 1000:.2f} V" if bat.isdigit() else bat,
                    "fw": str(data.get("fw") or ""),
                    "usb": str(data.get("usb") or "") == "1",
                }
        if "last_update" not in out:
            state = _find_state(body)
            if state:
                out["last_update"] = {"at": at, "state": state}
        if "wake" in out and "last_update" in out:
            break
    return out


def frames_overview(client: Any) -> tuple[list[dict[str, Any]], str]:
    """Every paperlesspaper frame on the account with its papers; (frames, error)."""
    frames: list[dict[str, Any]] = []
    try:
        orgs = client.organizations()
        for org in orgs:
            oid = API.ident(org)
            if not oid:
                continue
            for dev in client.devices(oid):
                did = API.ident(dev)
                if not did:
                    continue
                papers = []
                with contextlib.suppress(Exception):
                    papers = client.papers(device=did)
                events: list[dict[str, Any]] = []
                with contextlib.suppress(Exception):
                    events = client.events(did)
                active = API.ref(dev.get("paper"))
                frames.append(
                    {
                        "id": did,
                        "name": API.label(dev),
                        "status": str(dev.get("status") or ""),
                        "org": API.label(org),
                        "active": active,
                        "papers": [
                            {
                                "id": API.ident(p),
                                "name": API.label(p),
                                "kind": str(p.get("kind") or ""),
                                "updated": _when(p.get("imageUpdatedAt") or p.get("updatedAt")),
                                "active": API.ident(p) == active,
                            }
                            for p in papers
                            if API.ident(p)
                        ],
                        **wake_info(events),
                    }
                )
    except Exception as err:  # noqa: BLE001 - shown on the page
        return frames, str(err)
    return frames, ""


def blueprint() -> Any:
    bp = Blueprint("paperlesspaper_core_admin", __name__, template_folder="templates")
    bp.record_once(_start)

    def back() -> Any:
        return redirect(url_for("paperlesspaper_core_admin.index"))

    @bp.get("/")
    def index() -> Any:
        app = current_app._get_current_object()  # type: ignore[attr-defined]
        attach(app)
        st = settings_of(app.config.get("SETTINGS_STORE"))
        has_key = bool(str(st.get("api_key") or "").strip())
        up = uploader(app)
        tesserae = []
        with contextlib.suppress(Exception):
            for device in up.devices():
                cfg = up.config(device.id)
                last = up.status(device.id)
                tesserae.append(
                    {
                        "id": device.id,
                        "name": getattr(device, "name", device.id),
                        "paper": str(cfg.get("paper_id") or ""),
                        "orientation": str(cfg.get("orientation") or "landscape"),
                        "last": {**last, "when": _when(last.get("at"))} if last else {},
                    }
                )
        frames, error = frames_overview(client_for(app, PAGE_TIMEOUT_S)) if has_key else ([], "")
        names = {p["id"]: p["name"] for f in frames for p in f["papers"]}
        for t in tesserae:
            t["paper_name"] = names.get(t["paper"], "")
        return render_template(
            "paperlesspaper_core/index.html",
            has_key=has_key,
            settings_url=settings_url(),
            tesserae=tesserae,
            frames=frames,
            error=error,
        )

    @bp.post("/key")
    def key() -> Any:
        """Save the paperlesspaper API key from the plugin page itself."""
        value = str(request.form.get("api_key") or "").strip()
        store = current_app.config.get("SETTINGS_STORE")
        if not value:
            flash("Paste an API key first.", "warn")
            return back()
        if store is None or not hasattr(store, "update_for_namespace"):
            flash("Settings are unavailable; set the key under Settings > Widgets > paperlesspaper.", "warn")
            return back()
        save_api_key(store, value)
        flash("API key saved.", "success")
        return back()

    @bp.post("/show")
    def show() -> Any:
        """Make a paper the one its frame shows: the Tesserae paper, or one
        of paperlesspaper's own integrations."""
        device = str(request.form.get("device") or "").strip()
        paper = str(request.form.get("paper") or "").strip()
        if not device or not paper:
            abort(400)
        try:
            client_for(current_app).show_paper(device, paper)
            flash("The frame shows this paper from its next wake-up (press its button to wake it now).", "success")
        except Exception as err:  # noqa: BLE001
            flash(f"Could not switch the paper: {err}", "warn")
        return back()

    @bp.post("/link")
    def link() -> Any:
        """Upload a Tesserae device's frames to this paper from now on."""
        device = str(request.form.get("tesserae_device") or "").strip()
        paper = str(request.form.get("paper") or "").strip()
        app = current_app._get_current_object()  # type: ignore[attr-defined]
        up = uploader(app)
        if device not in {d.id for d in up.devices()} or not paper:
            flash("Pick a Tesserae device of the paperlesspaper kind.", "warn")
            return back()
        store = app.config.get("SETTINGS_STORE")
        if hasattr(store, "update_item"):
            store.update_item("devices", device, {"paper_id": paper})
        else:  # Tesserae before update_item: merge into the devices section
            section = store.get_section("devices") or {}
            merged = dict(section.get(device) or {})
            merged["paper_id"] = paper
            store.patch_section("devices", {device: merged})
        sent, msg = up.send(device, force=True)
        flash(f"{device} now uploads to this paper. {msg}", "success" if sent else "warn")
        return back()

    @bp.post("/setup/device")
    def setup_device_route() -> Any:
        """JSON: {"id", "name", "orientation", "paper_id"?}: the device, made or updated."""
        app = current_app._get_current_object()  # type: ignore[attr-defined]
        body = request.get_json(silent=True) or {}
        code, out = setup_device(app, body if isinstance(body, dict) else {})
        return jsonify(out), code

    @bp.get("/setup/status")
    def setup_status() -> Any:
        """JSON: is Home Assistant reachable, is a paperlesspaper key set, which papers there are."""
        app = current_app._get_current_object()  # type: ignore[attr-defined]
        ha = configure_ha(app)
        reg = app.config.get("PLUGIN_REGISTRY")
        core = getattr(reg.get("ha_core"), "server_module", None) if reg is not None else None
        reachable = False
        with contextlib.suppress(Exception):
            reachable = bool(core and core.is_configured() and core.get_states())
        st = settings_of(app.config.get("SETTINGS_STORE"))
        has_key = bool(str(st.get("api_key") or "").strip())
        frames, error = frames_overview(client_for(app, PAGE_TIMEOUT_S)) if has_key else ([], "")
        return jsonify({"home_assistant": ha, "home_assistant_reachable": reachable, "api_key": has_key, "frames": frames, "error": error})

    @bp.post("/send")
    def send() -> Any:
        device = str(request.form.get("tesserae_device") or "").strip()
        app = current_app._get_current_object()  # type: ignore[attr-defined]
        up = uploader(app)
        if device not in {d.id for d in up.devices()}:
            abort(404)
        sent, msg = up.send(device, force=True)
        flash(msg, "success" if sent else "warn")
        return back()

    return bp
