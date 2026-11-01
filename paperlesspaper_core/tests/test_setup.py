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
