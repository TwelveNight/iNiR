#!/usr/bin/env python3
"""Check desktop handoff and exit races without changing the real session."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


session = module("desktop_session", "scripts/personal/desktop-session.py")
config = module("session_config", "scripts/personal/configure-session.py")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.manager = {}

    def fake_run(self, *args, env=None):
        self.calls.append(args)
        output = "\n".join(f"{k}={v}" for k, v in self.manager.items()) if args[-1] == "show-environment" else ""
        if args[:3] == ("systemctl", "--user", "unset-environment"):
            for name in args[3:]:
                self.manager.pop(name, None)
        if args[:3] == ("systemctl", "--user", "import-environment"):
            self.manager.update({name: env[name] for name in args[3:]})
        return subprocess.CompletedProcess(args, 0, output, "")

    def test_niri_replaces_hyprland_gpu_and_identity_without_leaking_private_environment(self):
        self.manager = {"HYPRLAND_INSTANCE_SIGNATURE": "old", "LIBVA_DRIVER_NAME": "nvidia", "AQ_DRM_DEVICES": "old"}
        env = dict(NIRI_SOCKET="new-niri", WAYLAND_DISPLAY="wayland-1", XDG_CURRENT_DESKTOP="niri",
                   __NV_PRIME_RENDER_OFFLOAD="1", __GLX_VENDOR_LIBRARY_NAME="nvidia",
                   AQ_DRM_DEVICES="inherited", LIBVA_DRIVER_NAME="inherited", API_TOKEN="do-not-import")
        with patch.object(session, "run", self.fake_run):
            session.publish_environment("niri", env)
        self.assertNotIn("HYPRLAND_INSTANCE_SIGNATURE", self.manager)
        self.assertNotIn("AQ_DRM_DEVICES", self.manager)
        self.assertNotIn("LIBVA_DRIVER_NAME", self.manager)
        self.assertNotIn("API_TOKEN", str(self.calls))
        self.assertEqual(self.manager["__GLX_VENDOR_LIBRARY_NAME"], "nvidia")
        self.assertEqual(self.manager["XDG_SESSION_DESKTOP"], "niri")
        dbus = next(c for c in self.calls if c[0] == "dbus-update-activation-environment")
        self.assertIn("HYPRLAND_INSTANCE_SIGNATURE=", dbus)

    def test_hyprland_removes_niri_offload_and_restores_its_own_gpu_selection(self):
        self.manager = {"NIRI_SOCKET": "old", "__NV_PRIME_RENDER_OFFLOAD": "1", "DRI_PRIME": "AMD-shell"}
        env = dict(HYPRLAND_INSTANCE_SIGNATURE="new-hypr", WAYLAND_DISPLAY="wayland-2",
                   AQ_DRM_DEVICES="nvidia:amd", LIBVA_DRIVER_NAME="nvidia", __GLX_VENDOR_LIBRARY_NAME="nvidia",
                   NIRI_SOCKET="inherited", __NV_PRIME_RENDER_OFFLOAD="1")
        with patch.object(session, "run", self.fake_run):
            session.publish_environment("hyprland", env)
        self.assertNotIn("NIRI_SOCKET", self.manager)
        self.assertNotIn("__NV_PRIME_RENDER_OFFLOAD", self.manager)
        self.assertNotIn("DRI_PRIME", self.manager)
        self.assertEqual(self.manager["AQ_DRM_DEVICES"], "nvidia:amd")
        self.assertEqual(self.manager["XDG_CURRENT_DESKTOP"], "Hyprland")

    def test_old_watcher_does_not_stop_new_compositor_or_shared_wallpaper(self):
        self.manager = {"NIRI_SOCKET": "new", "WAYLAND_DISPLAY": "wayland-1"}
        identity = dict(desktop="niri", pid=123, key="NIRI_SOCKET", value="old", wayland="wayland-1")
        with patch.object(session, "run", self.fake_run):
            session.retire(identity)
        self.assertEqual(len(self.calls), 1)

    def test_compositor_exit_stops_wallpaper_before_clearing_environment(self):
        self.manager = {"HYPRLAND_INSTANCE_SIGNATURE": "own", "WAYLAND_DISPLAY": "wayland-2", "AQ_DRM_DEVICES": "nvidia"}
        identity = dict(desktop="hyprland", pid=123, key="HYPRLAND_INSTANCE_SIGNATURE", value="own", wayland="wayland-2")
        with patch.object(session, "run", self.fake_run):
            session.retire(identity)
        self.assertEqual(self.calls[1], ("systemctl", "--user", "stop", "ii-skwd-wall-theme.service", "skwd-walld.service"))
        self.assertEqual(self.calls[2], ("systemctl", "--user", "stop", "hyprland-session.target"))
        self.assertEqual(self.manager, {})

    def test_pidfd_wakes_on_actual_process_exit_without_polling_or_pid_reuse(self):
        child = subprocess.Popen(["sleep", "0.1"])
        try:
            with os.fdopen(os.pidfd_open(child.pid), "rb", buffering=0) as fd:
                self.assertEqual(session.select.select([fd], [], [], 2)[0], [fd])
        finally:
            child.wait()

    def test_watcher_launched_after_compositor_exit_still_retires_the_session(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            state = runtime / "inir/desktop-session.json"
            state.parent.mkdir()
            identity = dict(desktop="niri", pid=99999999, key="NIRI_SOCKET", value="own", wayland="wayland-1")
            state.write_text(json.dumps(identity))
            self.manager = {"NIRI_SOCKET": "own", "WAYLAND_DISPLAY": "wayland-1"}
            argv = ["desktop-session.py", "watch", "niri", "--identity", json.dumps(identity)]
            with patch.dict(os.environ, XDG_RUNTIME_DIR=str(runtime)), patch("sys.argv", argv), patch.object(session, "run", self.fake_run):
                session.main()
            self.assertFalse(state.exists())
            self.assertIn(("systemctl", "--user", "stop", "ii-skwd-wall-theme.service", "skwd-walld.service"), self.calls)

    def test_hook_migration_preserves_custom_apps_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            hooks = base / "hypr/hyprland/execs.lua"
            custom = base / "hypr/custom/execs.lua"
            hooks.parent.mkdir(parents=True)
            custom.parent.mkdir(parents=True)
            hooks.write_text('hl.on("hyprland.start", function()\n'
                '    hl.exec_cmd("my-app")\n'
                '    hl.exec_cmd("dbus-update-activation-environment --all")\n'
                '    hl.exec_cmd("$HOME/.config/hypr/custom/scripts/__restore_video_wallpaper.sh")\nend)\n')
            custom.write_text('hl.exec_cmd("my-custom-app")\n')
            config.configure_desktop_sessions(base)
            first = hooks.read_text(), custom.read_text()
            self.assertIn('hl.exec_cmd("my-app")', first[0])
            self.assertNotIn("dbus-update", first[0])
            self.assertNotIn("__restore_video", first[0])
            self.assertIn('hl.exec_cmd("my-custom-app")', first[1])
            config.configure_desktop_sessions(base)
            self.assertEqual((hooks.read_text(), custom.read_text()), first)

    def test_unknown_environment_hook_is_rejected_without_overwriting_hyprland(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            hooks = base / "hypr/hyprland/execs.lua"
            custom = base / "hypr/custom/execs.lua"
            hooks.parent.mkdir(parents=True)
            custom.parent.mkdir(parents=True)
            original = 'hl.exec_cmd("my-special-import-environment")\n'
            hooks.write_text(original)
            custom.write_text("keep custom")
            with self.assertRaises(ValueError):
                config.configure_desktop_sessions(base)
            self.assertEqual(hooks.read_text(), original)
            self.assertEqual(custom.read_text(), "keep custom")


if __name__ == "__main__":
    unittest.main()
