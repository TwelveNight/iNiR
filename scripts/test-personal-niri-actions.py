#!/usr/bin/env python3
"""Test personal workspace/floating semantics without touching the desktop."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "actions", Path(__file__).parent / "personal/niri-actions.py")
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)
ROOT = Path(__file__).resolve().parents[1]


class ActionsTests(unittest.TestCase):
    def fixture(self, name):
        return {
            "workspaces": [
                {"id": 11, "idx": 1, "output": "eDP-2", "is_focused": True},
                {"id": 17, "idx": 2, "output": "eDP-2"},
                {"id": 22, "idx": 9, "output": "HDMI-A-1"},
            ],
            "windows": [{"id": 71, "workspace_id": 11}],
            "focused-window": {"id": 71, "is_floating": False},
        }[name]

    def test_empty_workspace_stays_on_focused_output_and_uses_id(self):
        with patch.object(actions, "query", side_effect=self.fixture), \
                patch.object(actions, "request_action") as send:
            actions.empty_workspace()
            send.assert_called_once_with({"FocusWorkspace": {"reference": {"Id": 17}}})

    def test_empty_move_targets_window_id_and_follows(self):
        with patch.object(actions, "query", side_effect=self.fixture), \
                patch.object(actions, "request_action") as send:
            actions.empty_workspace(True)
            send.assert_called_once_with({"MoveWindowToWorkspace": {
                "window_id": 71, "reference": {"Id": 17}, "focus": True}})

    def test_occupied_trailing_workspace_is_not_used(self):
        def occupied(name):
            return [{"id": 72, "workspace_id": 17}] if name == "windows" else self.fixture(name)
        with patch.object(actions, "query", side_effect=occupied), \
                patch.object(actions, "request_action") as send:
            with self.assertRaises(RuntimeError):
                actions.empty_workspace(True)
            send.assert_not_called()

    def test_no_focused_window_does_not_move_another_window(self):
        def empty(name):
            return None if name == "focused-window" else self.fixture(name)
        with patch.object(actions, "query", side_effect=empty), \
                patch.object(actions, "request_action") as send:
            actions.empty_workspace(True)
            send.assert_not_called()

    def test_float_centers_and_sizes_only_the_original_window(self):
        with patch.object(actions, "query", side_effect=self.fixture), \
                patch.object(actions, "action") as act:
            actions.toggle_float()
            self.assertEqual([c.args for c in act.call_args_list], [
                ("move-window-to-floating", "--id", 71),
                ("set-window-width", "--id", 71, "50%"),
                ("set-window-height", "--id", 71, "60%"),
                ("center-window", "--id", 71),
            ])

    def test_return_to_tiling_does_not_resize_the_column(self):
        with patch.object(actions, "query", return_value={"id": 71, "is_floating": True}), \
                patch.object(actions, "action") as act:
            actions.toggle_float()
            act.assert_called_once_with("move-window-to-tiling", "--id", 71)


class HudFocusTests(unittest.TestCase):
    def run_toggle(self, windows):
        with patch.object(actions, "query", return_value=windows), \
                patch.object(actions, "action") as act:
            actions.main("hud-focus")
            return [call.args for call in act.call_args_list]

    def test_focus_exact_hud_from_another_app(self):
        windows = [
            {"id": 1, "app_id": "firefox", "title": "Hermes HUD", "is_focused": True},
            {"id": 2, "app_id": "hermes", "title": "Hermes"},
            {"id": 42, "app_id": "hermes", "title": "Hermes HUD"},
        ]
        self.assertEqual(self.run_toggle(windows), [("focus-window", "--id", 42)])

    def test_hud_returns_to_most_recent_other_window(self):
        windows = [
            {"id": 42, "app_id": "hermes", "title": "Hermes HUD", "is_focused": True},
            {"id": 7, "focus_timestamp": {"secs": 5, "nanos": 1}},
            {"id": 9, "focus_timestamp": {"secs": 5, "nanos": 2}},
            {"id": 3},
        ]
        self.assertEqual(self.run_toggle(windows), [("focus-window", "--id", 9)])

    def test_closed_return_window_falls_back_without_stale_ids(self):
        windows = [
            {"id": 77, "app_id": "hermes", "title": "Hermes HUD", "is_focused": True},
            {"id": 8, "focus_timestamp": {"secs": 10, "nanos": 0}},
        ]
        self.assertEqual(self.run_toggle(windows), [("focus-window", "--id", 8)])

    def test_missing_hud_is_noop(self):
        self.assertEqual(self.run_toggle([{"id": 7, "is_focused": True}]), [])

    def test_hud_alone_and_pet_overlay_do_not_steal_return_focus(self):
        hud = {"id": 42, "app_id": "hermes", "title": "Hermes HUD", "is_focused": True}
        pet = {"id": 3, "app_id": "hermes", "title": "Hermes Pet Overlay"}
        self.assertEqual(self.run_toggle([hud, pet]), [])


class KeybindIsolationTests(unittest.TestCase):
    def test_ui_overrides_and_removal_leave_upstream_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            shutil.copytree(ROOT / "defaults/niri", config / "niri")
            env = dict(os.environ, XDG_CONFIG_HOME=directory)
            stock = config / "niri/config.d/70-binds.kdl"
            before = stock.read_bytes()

            def command(*args):
                result = subprocess.run(["python3", str(ROOT / "scripts/niri-config.py"), *args],
                                        env=env, capture_output=True, text=True, check=True)
                return json.loads(result.stdout)

            listing = command("get-binds")
            active = {b["key_combo"]: b for b in listing["binds"] if not b["commented"]}
            self.assertEqual(active["Mod+H"]["action"], "move-column-left")
            self.assertEqual(active["Mod+Q"]["action"], "close-window")
            self.assertIn('"browser"', active["Mod+F"]["action"])
            self.assertIn("75-personal-binds.kdl", listing["config_file"])
            self.assertEqual(active["Mod+Shift+O"]["action"], "toggle-windowed-fullscreen")
            self.assertNotIn("Mod+D", active)
            self.assertTrue(command("set-bind", "Mod+T", 'spawn "kitty"')["success"])
            self.assertEqual(stock.read_bytes(), before)
            self.assertTrue(command("remove-bind", "Mod+T")["success"])
            self.assertEqual(stock.read_bytes(), before)
            result = subprocess.check_output([
                "python3", str(ROOT / "scripts/parse_niri_keybinds.py"),
                str(config / "niri/config.kdl")], text=True, env=env)
            rows = [b for c in json.loads(result)["children"]
                    for group in c["children"] for b in group["keybinds"]]
            self.assertFalse(any(b["key"].lower() == "t" and b["mods"] == ["Super"] for b in rows))
            subprocess.run(["niri", "validate", "--config", str(config / "niri/config.kdl")],
                           capture_output=True, check=True)


if __name__ == "__main__":
    unittest.main()
