"""paperlesspaper Core: Home Assistant Core pointed at Supervisor inside the app."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def test_configure_ha_points_core_at_supervisor() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("pp_server_ha", Path(__file__).resolve().parents[1] / "server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    class Store:
        def __init__(self, cur):
            self.cur, self.saved = cur, None

        def get_for_runtime(self, ns, pid, fields):
            return dict(self.cur)

        def update_for_namespace(self, ns, pid, values, fields):
            self.saved = (ns, pid, values)

    class Plugin:
        manifest = {"settings": [{"name": "base_url"}, {"name": "token", "secret": True}, {"name": "verify_tls"}]}

    class Reg:
        def get(self, pid):
            return Plugin() if pid == "ha_core" else None

    env = {"TESSERAE_HA_INGRESS": "1", "SUPERVISOR_TOKEN": "t0k"}
    class App:
        def __init__(self, store):
            self.config = {"SETTINGS_STORE": store, "PLUGIN_REGISTRY": Reg()}

    blank = Store({})
    assert srv.configure_ha(App(blank), env) == "set"
    assert blank.saved == ("plugins", "ha_core", {"base_url": "http://supervisor/core", "token": "t0k", "verify_tls": True})
    own = Store({"base_url": "http://ha.local:8123"})
    assert srv.configure_ha(App(own), env) == "kept" and own.saved is None
    again = Store({"base_url": "http://supervisor/core"})
    assert srv.configure_ha(App(again), env) == "set"  # a new token after an update
    assert srv.configure_ha(App(Store({})), {}) == "skipped"


def test_device_values_on_an_older_tesserae() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("pp_server_dev", Path(__file__).resolve().parents[1] / "server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    class Old:
        def __init__(self):
            self.section = {"pp": {"paper_id": "p1"}}

        def get_section(self, name):
            return self.section

        def patch_section(self, name, values):
            self.section.update(values)

    st = Old()
    srv.save_device_values(st, "pp", {"orientation": "portrait"})
    assert st.section["pp"] == {"paper_id": "p1", "orientation": "portrait"}
    assert srv.DEVICE_ID.match("paperlesspaper_l") and not srv.DEVICE_ID.match("L")


def test_configure_host_names_the_app_while_the_port_is_closed() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("pp_server_host", Path(__file__).resolve().parents[1] / "server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    closed = lambda t: {"hostname": "abc-tesserae-paperless", "network": {"8765/tcp": None}}  # noqa: E731
    opened = lambda t: {"hostname": "abc-tesserae-paperless", "network": {"8765/tcp": 8765}}  # noqa: E731
    app_env = {"TESSERAE_HA_INGRESS": "1", "SUPERVISOR_TOKEN": "t"}

    env = dict(app_env)
    assert srv.configure_host(env, closed) == "set" and env["TESSERAE_HOST_IP"] == "abc-tesserae-paperless"
    # The port opened later: back to Tesserae's own LAN address.
    assert srv.configure_host(env, opened) == "kept" and "TESSERAE_HOST_IP" not in env
    # An address of the user's own is kept, and outside the app nothing changes.
    env = {**app_env, "TESSERAE_HOST_IP": "10.0.0.2"}
    assert srv.configure_host(env, closed) == "kept" and env["TESSERAE_HOST_IP"] == "10.0.0.2"
    assert srv.configure_host({}, closed) == "skipped"
