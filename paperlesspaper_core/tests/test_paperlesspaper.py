"""Offline tests for the paperlesspaper plugin and device kind: the network is
faked, Tesserae's registries are stand-ins, and the page renders against stub
base templates. Run from the repo root: python -m pytest paperlesspaper_core/tests -q"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "paperlesspaper_core"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


API = _load(CORE / "lib" / "api.py", "pp_test_api")
PUB = _load(CORE / "lib" / "publisher.py", "pp_test_publisher")
DEV = _load(ROOT / "devices" / "paperlesspaper" / "device.py", "pp_test_device")

PNG = b"\x89PNG\r\n\x1a\nfake"


# ----------------------------------------------------------------------
# the network, faked
# ----------------------------------------------------------------------
class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *a: Any) -> None:
        self.close()


class Calls(list):  # type: ignore[type-arg]
    def __init__(self) -> None:
        super().__init__()
        self.answers: list[Any] = []


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every request; answers from ``calls.answers`` (a list of bytes or
    exceptions, used in turn), else ``{}``."""
    seen = Calls()
    answers = seen.answers

    def urlopen(req: Any, timeout: float = 0) -> Any:
        seen.append(req)
        got = answers.pop(0) if answers else b"{}"
        if isinstance(got, Exception):
            raise got
        return FakeResponse(got)

    monkeypatch.setattr(API.urllib.request, "urlopen", urlopen)
    return seen


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(b'{"message":"nope"}'))  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# the API client
# ----------------------------------------------------------------------
def test_upload_is_multipart_with_the_key(calls: list[Any]) -> None:
    API.Client("secret-key").upload("abc123", PNG, {"orientation": "landscape"})
    req = calls[0]
    assert req.get_method() == "POST"
    assert req.full_url == "https://api.paperlesspaper.de/v1/papers/uploadSingleImage/abc123"
    assert req.get_header("X-api-key") == "secret-key"
    ctype = req.get_header("Content-type")
    assert ctype.startswith("multipart/form-data; boundary=")
    boundary = ctype.split("boundary=")[1].encode()
    body = req.data
    assert b'name="picture"; filename="tesserae.png"' in body and PNG in body
    assert b'name="settings"\r\n\r\n{"orientation": "landscape"}' in body
    assert body.rstrip().endswith(b"--" + boundary + b"--")


def test_no_key_and_errors_say_why(calls: list[Any]) -> None:
    with pytest.raises(API.ApiError) as err:
        API.Client("").upload("abc", PNG)
    assert err.value.auth and not calls
    calls.answers.append(http_error(401))  # type: ignore[attr-defined]
    with pytest.raises(API.ApiError) as err:
        API.Client("k").upload("abc", PNG)
    assert err.value.auth and not err.value.retryable and "refused the API key" in str(err.value)
    calls.answers.append(http_error(503))  # type: ignore[attr-defined]
    with pytest.raises(API.ApiError) as err:
        API.Client("k").upload("abc", PNG)
    assert err.value.retryable
    calls.answers.append(urllib.error.URLError("down"))  # type: ignore[attr-defined]
    with pytest.raises(API.ApiError) as err:
        API.Client("k").papers(device="d1")
    assert err.value.retryable and "could not be reached" in str(err.value)


def test_lists_and_switching_the_paper(calls: list[Any]) -> None:
    calls.answers.extend(  # type: ignore[attr-defined]
        [
            json.dumps({"results": [{"id": "p1", "kind": "image", "meta": {"pluginManifest": {"name": "Daily XKCD"}}}], "page": 1}).encode(),
            json.dumps([{"id": "d1", "name": "Kitchen"}]).encode(),
            b"{}",
        ]
    )
    c = API.Client("k")
    papers = c.papers(device="d1")
    assert API.ident(papers[0]) == "p1" and API.label(papers[0]) == "Daily XKCD"
    assert "deviceId=d1" in calls[0].full_url
    assert [API.label(d) for d in c.devices("org1")] == ["Kitchen"]
    assert "organization=org1" in calls[1].full_url
    c.show_paper("d1", "p1")
    assert calls[2].get_method() == "PATCH" and calls[2].full_url.endswith("/devices/d1")
    assert json.loads(calls[2].data) == {"paper": "p1"}
    assert API.ref({"_id": "x"}) == "x" and API.ref("y") == "y" and API.ref(None) == ""


# ----------------------------------------------------------------------
# the uploader
# ----------------------------------------------------------------------
class FakeClient:
    def __init__(self, fail: list[Exception] | None = None) -> None:
        self.sent: list[tuple[str, bytes, Any]] = []
        self.fail = list(fail or [])

    def upload(self, paper: str, png: bytes, settings: Any = None) -> None:
        if self.fail:
            raise self.fail.pop(0)
        self.sent.append((paper, png, settings))


class FakeEvents:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def record(self, **kw: Any) -> int:
        self.rows.append(kw)
        return len(self.rows)


def make(tmp_path: Path, *, cfg: dict[str, Any] | None = None, client: FakeClient | None = None, digest: str = "d1") -> Any:
    renders = tmp_path / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / f"{digest}.png").write_bytes(PNG)
    devices = SimpleNamespace(
        devices={
            "frame": SimpleNamespace(id="frame", kind_of="paperlesspaper", name="Frame"),
            "kindle": SimpleNamespace(id="kindle", kind_of="koreader_client", name="Kindle"),
            "paperlesspaper": SimpleNamespace(id="paperlesspaper", kind_of=None, name="the kind itself"),
        }
    )
    section = {"frame": {"paper_id": "paper1", "orientation": "portrait", **(cfg or {})}, "kindle": {"paper_id": "x"}}
    settings = SimpleNamespace(get_section=lambda name: section if name == "devices" else {})
    latest = {"frame": {"composition_digest": digest}, "kindle": {"composition_digest": digest}}
    client = client or FakeClient()
    events = FakeEvents()
    up = PUB.Uploader(
        devices=devices,
        settings=settings,
        renders_dir=renders,
        latest_render_fn=latest.get,
        client_fn=lambda: client,
        state_path=tmp_path / "state" / "sent.json",
        event_log=events,
        run_async=False,
        retry_wait_s=0,
    )
    return SimpleNamespace(up=up, client=client, events=events, latest=latest, renders=renders, section=section)


def test_each_new_frame_is_uploaded_once(tmp_path: Path) -> None:
    t = make(tmp_path)
    t.up.on_push()
    assert t.client.sent == [("paper1", PNG, {"orientation": "portrait"})], "only the paperlesspaper device"
    t.up.on_push()
    assert len(t.client.sent) == 1, "the same frame is not sent again"
    again = make(tmp_path, client=t.client)  # a restart reads what was sent
    again.up.on_push()
    assert len(t.client.sent) == 1
    (t.renders / "d2.png").write_bytes(PNG + b"2")
    again.latest["frame"]["composition_digest"] = "d2"
    again.up.on_push()
    assert len(t.client.sent) == 2 and t.client.sent[-1][1] == PNG + b"2"
    assert [r["status"] for r in again.events.rows] == ["ok"]
    sent, _msg = again.up.send("frame", force=True)
    assert sent and len(t.client.sent) == 3, "Upload now sends whatever was sent before"


def test_a_new_paper_gets_the_frame_again(tmp_path: Path) -> None:
    t = make(tmp_path)
    t.up.on_push()
    t.section["frame"]["paper_id"] = "paper2"
    t.up.on_push()
    assert [s[0] for s in t.client.sent] == ["paper1", "paper2"]


def test_without_a_paper_or_frame_nothing_is_sent(tmp_path: Path) -> None:
    t = make(tmp_path, cfg={"paper_id": ""})
    sent, msg = t.up.send("frame")
    assert not sent and "No paper" in msg and not t.client.sent
    t = make(tmp_path / "b")
    t.latest["frame"] = {}
    sent, msg = t.up.send("frame")
    assert not sent and "Nothing rendered" in msg
    t.latest["frame"] = {"composition_digest": "gone"}
    sent, msg = t.up.send("frame")
    assert not sent and "no longer on disk" in msg


def test_a_server_error_is_retried_once_a_refused_key_is_not(tmp_path: Path) -> None:
    t = make(tmp_path, client=FakeClient([API.ApiError("busy", status=503)]))
    sent, _ = t.up.send("frame")
    assert sent and len(t.client.sent) == 1
    t = make(tmp_path / "b", client=FakeClient([API.ApiError("refused", status=401), API.ApiError("x", status=401)]))
    sent, msg = t.up.send("frame")
    assert not sent and "refused" in msg and len(t.client.fail) == 1, "no retry on a refused key"
    assert t.up.status("frame")["ok"] is False and t.events.rows[-1]["status"] == "failed"
    t.client.fail.clear()
    sent, _ = t.up.send("frame")
    assert sent, "a failed upload is tried again on the next push"


def test_a_listener_never_raises(tmp_path: Path) -> None:
    t = make(tmp_path)
    t.up._devices = None  # noqa: SLF001 - a registry the host has not built yet
    t.up.on_push()  # no exception


# ----------------------------------------------------------------------
# the device kind
# ----------------------------------------------------------------------
def test_device_kind() -> None:
    manifest = json.loads((ROOT / "devices" / "paperlesspaper" / "device.json").read_text())
    assert manifest["transport"] == "push" and manifest["renderers"] == ["pi_png"]
    assert (manifest["panel"]["w"], manifest["panel"]["h"]) == (1600, 1200)
    assert DEV.validate_config({"paper_id": "682fd0d7d4a6325d9d45b86d", "orientation": "portrait"}) == (True, None)
    assert DEV.validate_config({"paper_id": ""}) == (True, None)
    assert DEV.validate_config({"paper_id": "has spaces/slash"})[0] is False
    assert DEV.validate_config({"paper_id": 5})[0] is False
    assert DEV.validate_config({"orientation": "sideways"})[0] is False
    assert DEV.parse_status(b'{"bat": 1}') == {"bat": 1} and DEV.parse_status(b"x") == {"raw": "x"}
    schema = ROOT.parent / "tesserae" / "schema" / "device.schema.json"
    if schema.exists():  # a Tesserae checkout beside this repo
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.validate(manifest, json.loads(schema.read_text()))


# ----------------------------------------------------------------------
# the page
# ----------------------------------------------------------------------
flask = pytest.importorskip("flask")

STUBS = {
    "_base.html": "<html>{% with messages = get_flashed_messages(with_categories=true) %}{% for c, m in messages %}<p class='flash-{{ c }}'>{{ m }}</p>{% endfor %}{% endwith %}{% block main %}{% endblock %}</html>",
    "_components.html": (
        "{% macro card_head(title, icon_name=None, level=2, blurb=None, action=None) %}<h2>{{ title }}</h2>{% endmacro %}"
        "{% macro button(label, variant='primary', type='submit', name=None, value=None, full_width=False, title=None, disabled=False, icon=None) %}"
        "<button{% if disabled %} disabled{% endif %}>{{ label }}</button>{% endmacro %}"
    ),
}


class Store:
    def __init__(self, key: str) -> None:
        self.key = key
        self.devices: dict[str, Any] = {"frame": {"paper_id": "", "orientation": "landscape"}}

    def get_for_runtime(self, ns: str, pid: str, fields: Any) -> dict[str, Any]:
        return {"api_key": self.key, "api_base": "https://api.example/v1"}

    def get_section(self, name: str) -> dict[str, Any]:
        return self.devices if name == "devices" else {}

    def patch_section(self, name: str, values: dict[str, Any]) -> None:
        self.devices.update(values)


class Push:
    def __init__(self) -> None:
        self.listeners: list[Any] = []
        self.latest: dict[str, Any] = {}

    def add_listener(self, cb: Any) -> None:
        if cb not in self.listeners:
            self.listeners.append(cb)

    def latest_render_for(self, device_id: str) -> Any:
        return self.latest.get(device_id)


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    server = _load(CORE / "server.py", "pp_test_server")
    monkeypatch.setattr(server, "_watch", lambda app: None)
    a = flask.Flask("t")
    a.secret_key = "t"
    import jinja2

    a.jinja_loader = jinja2.ChoiceLoader([jinja2.DictLoader(STUBS), a.jinja_loader])  # type: ignore[assignment,list-item]
    renders = tmp_path / "renders"
    renders.mkdir()
    (renders / "c1.png").write_bytes(PNG)
    push = Push()
    push.latest["frame"] = {"composition_digest": "c1"}
    a.config.update(
        SETTINGS_STORE=Store("k"),
        PUSH_MANAGER=push,
        RENDERS_DIR=renders,
        DATA_ROOT=str(tmp_path),
        DEVICE_REGISTRY=SimpleNamespace(devices={"frame": SimpleNamespace(id="frame", kind_of="paperlesspaper", name="Frame")}),
    )
    a.register_blueprint(server.blueprint(), url_prefix="/plugins/paperlesspaper_core")

    @a.get("/plugins/", endpoint="plugins.plugins_index")
    def _index() -> str:
        return ""

    a.config["server"] = server
    return a


def test_the_uploader_hangs_on_the_push_pipeline(app: Any) -> None:
    assert len(app.config["PUSH_MANAGER"].listeners) == 1
    app.config["server"].attach(app)
    assert len(app.config["PUSH_MANAGER"].listeners) == 1, "attached once"


def test_page_lists_frames_switches_and_links(app: Any, calls: list[Any]) -> None:
    calls.answers.extend(  # type: ignore[attr-defined]
        [
            json.dumps([{"id": "org1", "name": "Home"}]).encode(),
            json.dumps([{"id": "dev1", "name": "Living room", "status": "online", "paper": "p-xkcd"}]).encode(),
            json.dumps(
                {
                    "results": [
                        {"id": "p-xkcd", "kind": "plugin", "meta": {"pluginManifest": {"name": "Daily XKCD"}}},
                        {"id": "p-tess", "kind": "image", "title": "Tesserae"},
                    ]
                }
            ).encode(),
            json.dumps(
                [
                    {"id": "e1", "type": "activate", "payload": {"json": '{"fw":"b3.0.10","bat":"3749","wake":"BUTTON","usb":"0"}'}, "timestamp": "2026-11-01T10:00:00Z"},
                    {"id": "e2", "type": "state", "payload": {"state": "update_ok"}, "timestamp": "2026-11-01T10:00:05Z"},
                ]
            ).encode(),
        ]
    )
    page = app.test_client().get("/plugins/paperlesspaper_core/").get_data(as_text=True)
    assert "Living room" in page and "Daily XKCD" in page and "Tesserae" in page
    assert "on the frame" in page and "3.75 V" in page, page
    assert "(button)" in page and "update ok" in page, page
    assert calls[0].full_url == "https://api.example/v1/organizations/"

    calls.clear()
    r = app.test_client().post("/plugins/paperlesspaper_core/show", data={"device": "dev1", "paper": "p-tess"})
    assert r.status_code == 302 and calls[0].get_method() == "PATCH" and json.loads(calls[0].data) == {"paper": "p-tess"}

    calls.clear()
    r = app.test_client().post("/plugins/paperlesspaper_core/link", data={"tesserae_device": "frame", "paper": "p-tess"})
    assert r.status_code == 302
    assert app.config["SETTINGS_STORE"].devices["frame"]["paper_id"] == "p-tess"
    assert calls[0].full_url.endswith("/papers/uploadSingleImage/p-tess"), "linking uploads the current frame"


def test_page_without_a_key(app: Any, calls: list[Any]) -> None:
    app.config["SETTINGS_STORE"].key = ""
    page = app.test_client().get("/plugins/paperlesspaper_core/").get_data(as_text=True)
    assert "Add your API key" in page and not calls
