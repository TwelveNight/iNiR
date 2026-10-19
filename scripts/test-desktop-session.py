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
        output = json.dumps(self.manager) if "show-environment" in args else ""
        if args[:3] == ("systemctl", "--user", "unset-environment"):
            for name in args[3:]:
                self.manager.pop(name, None)
        if args[:3] == ("systemctl", "--user", "import-environment"):
            self.manager.update({name: env[name] for name in args[3:]})
        if args[0] == "dbus-update-activation-environment":
            # The host's dbus-broker mirrors updates back into the user manager.
            self.manager.update(dict(arg.split("=", 1) for arg in args[1:]))
        return subprocess.CompletedProcess(args, 0, output, "")

    def test_manager_environment_preserves_platform_fallback_and_escaped_values(self):
        self.manager = dict(QT_QPA_PLATFORM="wayland;xcb", XCURSOR_THEME="theme with spaces",
                            DISPLAY=":0", XMODIFIERS="@im=fcitx")
        with patch.object(session, "run", self.fake_run):
            self.assertEqual(session.manager_environment(), self.manager)
        self.assertEqual(self.calls, [("systemctl", "--user", "show-environment", "--output=json")])

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

    def test_inherited_empty_gpu_placeholders_are_not_reimported(self):
        for desktop in ("niri", "hyprland"):
            with self.subTest(desktop=desktop):
                env = dict(WAYLAND_DISPLAY="wayland-1", __EGL_VENDOR_LIBRARY_FILENAMES="",
                           DRI_PRIME="", VK_LOADER_DRIVERS_DISABLE="",
                           QT_FFMPEG_DECODING_HW_DEVICE_TYPES="")
                with patch.object(session, "run", self.fake_run):
                    session.publish_environment(desktop, env)
                for name in ("__EGL_VENDOR_LIBRARY_FILENAMES", "DRI_PRIME", "VK_LOADER_DRIVERS_DISABLE"):
                    self.assertNotIn(name, self.manager)
                self.assertEqual(self.manager["QT_FFMPEG_DECODING_HW_DEVICE_TYPES"], "")

    def test_old_watcher_does_not_stop_new_compositor_or_shared_wallpaper(self):
        self.manager = {"NIRI_SOCKET": "new", "WAYLAND_DISPLAY": "wayland-1"}
        identity = dict(desktop="niri", pid=123, key="NIRI_SOCKET", value="old", wayland="wayland-1")
        with patch.object(session, "run", self.fake_run):
            session.retire(identity)
        self.assertEqual(len(self.calls), 1)

    def test_ready_requires_current_compositor_and_completed_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            identity = dict(desktop="niri", pid=123, key="NIRI_SOCKET", value="new", wayland="wayland-1")
            self.manager = dict(XDG_CURRENT_DESKTOP="niri", NIRI_SOCKET="new", WAYLAND_DISPLAY="wayland-1")
            state = runtime / "desktop-session.json"
            state.write_text(json.dumps(dict(identity, value="old")))
            with patch.object(session, "run", self.fake_run), patch.object(session, "session_identity", return_value=identity):
                with self.assertRaises(ValueError):
                    session.ready_environment(runtime, "niri")
                state.write_text(json.dumps(identity))
                self.assertEqual(session.ready_environment(runtime, "niri"), self.manager)
                self.manager["XDG_CURRENT_DESKTOP"] = "Hyprland"
                with self.assertRaises(ValueError):
                    session.ready_environment(runtime, "niri")

    def test_autostart_waits_for_new_display_instead_of_using_active_old_target(self):
        directory = Path("/unused")
        env = dict(XDG_CURRENT_DESKTOP="niri", WAYLAND_DISPLAY="stale-display")
        with patch.object(session, "ready_environment", side_effect=[FileNotFoundError(), ValueError(), {}]) as ready, patch.object(session.time, "sleep"):
            session.wait_ready(directory, env, "app-kdeconnect@autostart.service")
        self.assertEqual(ready.call_count, 3)

    def test_autostart_timeout_refuses_dead_display_and_other_services_are_untouched(self):
        with patch.object(session, "ready_environment", side_effect=ValueError()) as ready:
            session.wait_ready(Path("/unused"), dict(XDG_CURRENT_DESKTOP="niri"), "app-custom.service")
            session.wait_ready(Path("/unused"), dict(XDG_CURRENT_DESKTOP="GNOME"), "app-custom@autostart.service")
            ready.assert_not_called()
            with self.assertRaisesRegex(ValueError, "refusing to launch"):
                session.wait_ready(Path("/unused"), dict(XDG_CURRENT_DESKTOP="Hyprland"), "app-kdeconnect@autostart.service", timeout=0)

    def test_hyprland_target_starts_with_persisted_identity_for_bound_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = dict(desktop="hyprland", pid=os.getpid(), key="HYPRLAND_INSTANCE_SIGNATURE", value="own", wayland="wayland-1")
            argv = ["desktop-session.py", "start", "hyprland", "--adopt"]
            def target_run(*args, env=None):
                if args == ("systemctl", "--user", "start", "hyprland-session.target"):
                    for name in ("desktop-session.json", "hyprland-session.json"):
                        self.assertEqual(json.loads((Path(directory) / "inir" / name).read_text()), identity)
                return self.fake_run(*args, env=env)
            with patch.dict(os.environ, XDG_RUNTIME_DIR=directory), patch("sys.argv", argv), patch.object(session, "session_identity", return_value=identity), patch.object(session, "unit_active", return_value=False), patch.object(session, "run", target_run):
                session.main()
            self.assertIn(("systemctl", "--user", "start", "hyprland-session.target"), self.calls)
            self.assertFalse(any(call[0] == "systemd-run" for call in self.calls))

    def test_compositor_exit_stops_wallpaper_before_clearing_environment(self):
        self.manager = {"HYPRLAND_INSTANCE_SIGNATURE": "own", "WAYLAND_DISPLAY": "wayland-2", "AQ_DRM_DEVICES": "nvidia"}
        identity = dict(desktop="hyprland", pid=123, key="HYPRLAND_INSTANCE_SIGNATURE", value="own", wayland="wayland-2")
        with patch.object(session, "run", self.fake_run):
            session.retire(identity)
        self.assertEqual(self.calls[1], ("systemctl", "--user", "stop", "ii-skwd-wall-theme.service", "skwd-walld.service"))
        self.assertEqual(self.calls[2], ("systemctl", "--user", "stop", "hyprland-session.target"))
        self.assertEqual(self.manager, {})

    def test_standard_niri_logout_clears_identity_before_watcher_without_leaking_gpu_values(self):
        self.manager = {"__GLX_VENDOR_LIBRARY_NAME": "nvidia", "__NV_PRIME_RENDER_OFFLOAD": "1"}
        identity = dict(desktop="niri", pid=123, key="NIRI_SOCKET", value="own", wayland="wayland-1")
        with patch.object(session, "run", self.fake_run):
            session.retire(identity)
        self.assertEqual(self.manager, {})

    def test_reused_wayland_socket_with_stale_identity_cannot_stop_new_desktop(self):
        self.manager = {"HYPRLAND_INSTANCE_SIGNATURE": "old", "WAYLAND_DISPLAY": "wayland-1", "XDG_CURRENT_DESKTOP": "niri"}
        identity = dict(desktop="hyprland", pid=123, key="HYPRLAND_INSTANCE_SIGNATURE", value="old", wayland="wayland-1")
        with patch.object(session, "run", self.fake_run):
            session.retire(identity)
        self.assertEqual(len(self.calls), 1)

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
            target = base / "systemd/user/hyprland-session.target"
            target.parent.mkdir(parents=True)
            original_target = '[Unit]\nDescription=Personal target\nPropagatesStopTo=graphical-session.target\nBindsTo=graphical-session.target\n'
            target.write_text(original_target)
            config.configure_desktop_sessions(base)
            first = hooks.read_text(), custom.read_text()
            self.assertTrue((base / "systemd/user/desktop-profile-hyprland-watch.service").exists())
            dropin = (base / "systemd/user/hyprland-session.target.d/40-compositor-lifetime.conf").read_text()
            self.assertIn("BindsTo=desktop-profile-hyprland-watch.service", dropin)
            self.assertNotIn("PropagatesStopTo", dropin)
            self.assertEqual(target.read_text(), original_target.replace('PropagatesStopTo=graphical-session.target\n', ''))
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
