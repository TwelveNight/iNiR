#!/usr/bin/env python3
"""Folia tray-close regressions; never interact with the user's desktop."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("actions", ROOT / "scripts/personal/niri-actions.py")
assert spec is not None and spec.loader is not None
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)


class FoliaCloseTests(unittest.TestCase):
    window = {"id": 20, "app_id": "folia-major", "pid": 12081, "title": "Folia"}
    service = "org.freedesktop.StatusNotifierItem-12081-1"

    def test_void_dbus_reply_is_success(self):
        with patch.object(actions.subprocess, "check_output", return_value=""):
            self.assertEqual(actions.bus_call("call", "fixture", "/menu", "fixture", "Event"), [])

    def run_hide(self, label="隐藏窗口", owner_pid=12081, enabled=True, windows=None):
        calls = []

        def reply(command, **kwargs):
            calls.append(command)
            if command[0] == "niri":
                return json.dumps([self.window] if windows is None else windows)
            if "ListNames" in command:
                result = [[self.service]]
            elif "GetNameOwner" in command:
                result = [":1.486"]
            elif "GetConnectionUnixProcessID" in command:
                result = [owner_pid]
            elif "get-property" in command:
                result = "/org/chromium/DbusMenu"
            elif "GetLayout" in command:
                item = {"type": "(ia{sv}av)", "data": [589, {
                    "label": {"type": "s", "data": label},
                    "enabled": {"type": "b", "data": enabled},
                }, []]}
                result = [42, [0, {}, [item]]]
            elif "Event" in command:
                result = []
            else:
                raise AssertionError(command)
            return json.dumps({"data": result})

        with patch.object(actions.subprocess, "check_output", side_effect=reply):
            actions.main("folia-hide", "20")
        return calls

    def test_hide_invokes_owned_tray_item_not_close_or_quit(self):
        calls = self.run_hide()
        event = next(c for c in calls if "Event" in c)
        self.assertEqual(event[-6:], ["isvu", "589", "clicked", "s", "", "0"])
        self.assertIn(":1.486", event)
        self.assertFalse(any("close-window" in c or "Quit" in c for c in calls))

    def test_repeated_hide_does_not_show_the_window(self):
        self.assertFalse(any("Event" in c for c in self.run_hide(label="显示窗口")))

    def test_missing_hide_item_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.run_hide(label="退出")

    def test_disabled_hide_item_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.run_hide(enabled=False)

    def test_wrong_tray_owner_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.run_hide(owner_pid=999)

    def test_closed_window_is_noop(self):
        self.assertEqual(len(self.run_hide(windows=[])), 1)

    def test_remote_control_window_is_not_hidden(self):
        with self.assertRaises(RuntimeError):
            self.run_hide(windows=[dict(self.window, title="Folia Remote")])


class CloseScriptTests(unittest.TestCase):
    def run_close(self, app_id="folia-major", helper_status=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "personal").mkdir()
            shutil.copyfile(ROOT / "scripts/close-window.sh", root / "close-window.sh")
            log = root / "calls.jsonl"
            niri = root / "niri"
            niri.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                            "with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
                            "if sys.argv[1:] == ['msg','-j','focused-window']: print(os.environ['WINDOW'])\n")
            niri.chmod(0o755)
            pgrep = root / "pgrep"
            pgrep.write_text("#!/bin/sh\nexit 1\n")
            pgrep.chmod(0o755)
            (root / "personal/niri-actions.py").write_text(
                "import json,os,sys\n"
                "with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
                "sys.exit(int(os.environ['HELPER_STATUS']))\n")
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       CALLS=str(log), WINDOW=json.dumps(dict(FoliaCloseTests.window, app_id=app_id),
                                                        separators=(",", ":")),
                       HELPER_STATUS=str(helper_status))
            result = subprocess.run(["bash", str(root / "close-window.sh")], env=env,
                                    capture_output=True, text=True)
            return result, [json.loads(line) for line in log.read_text().splitlines()]

    def test_folia_close_routes_to_tray_helper_without_shell_ipc(self):
        result, calls = self.run_close()
        self.assertEqual(result.returncode, 0)
        self.assertIn(["folia-hide", "20"], calls)
        self.assertFalse(any("close-window" in c for c in calls))

    def test_folia_helper_failure_never_falls_back_to_closing(self):
        result, calls = self.run_close(helper_status=1)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(any("close-window" in c for c in calls))

    def test_other_apps_keep_normal_close(self):
        result, calls = self.run_close(app_id="firefox")
        self.assertEqual(result.returncode, 0)
        self.assertIn(["msg", "action", "close-window", "--id", "20"], calls)


if __name__ == "__main__":
    unittest.main()
