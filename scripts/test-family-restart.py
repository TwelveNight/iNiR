#!/usr/bin/env python3
"""Run the real family helper with private fixtures and a fake supervisor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FamilyRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-family-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.private = self.config / "inir/config.json"
        self.ii = self.config / "illogical-impulse/config.json"
        self.original = {"panelFamily": "ii", "enabledPanels": ["iiBar"],
                         "knownPanels": ["iiBar"], "sentinel": "private"}
        for path, value in [(self.private, self.original),
                            (self.ii, dict(self.original, sentinel="II-do-not-write"))]:
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(value))
        self.ii_bytes = self.ii.read_bytes()
        self.log = self.base / "service.log"
        launcher = self.base / "fake-inir"
        launcher.write_text('''#!/bin/sh
printf '%s\n' "$*" >> "$INIR_FAMILY_SWITCH_TEST_LOG"
case "$2" in
stop) exit "${TEST_STOP_RC:-0}";;
start) exit "${TEST_START_RC:-0}";;
esac
exit 9
''')
        launcher.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.base), XDG_CONFIG_HOME=str(self.config),
                        XDG_STATE_HOME=str(self.base / "state"), XDG_CACHE_HOME=str(self.base / "cache"),
                        XDG_DATA_HOME=str(self.base / "data"), XDG_BIN_HOME=str(self.base / "bin"),
                        INIR_FAMILY_SWITCH_INIR=str(launcher), INIR_FAMILY_SWITCH_TEST_LOG=str(self.log),
                        PYTHONDONTWRITEBYTECODE="1")
        for key in ["INIR_CONFIG_DIR", "INIR_STATE_DIR", "INIR_RUNTIME_DIR", "INIR_VENV", "DOTS_CORE_CONFDIR"]:
            self.env.pop(key, None)

    def run_helper(self):
        return subprocess.run([sys.executable, str(ROOT / "scripts/switch-family-restart.py"),
                               "waffle", '["wBar","wBackground"]'], env=self.env,
                              capture_output=True, text=True, timeout=8)

    def assert_switch(self, path):
        path.chmod(0o640)
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ii.read_bytes(), self.ii_bytes, "helper wrote shared II settings")
        value = json.loads(path.read_text())
        self.assertEqual(value["panelFamily"], "waffle")
        self.assertEqual(value["enabledPanels"], ["iiBar", "wBar", "wBackground"])
        self.assertEqual(value["knownPanels"], ["iiBar", "wBar", "wBackground"])
        self.assertEqual(value["sentinel"], "private")
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.log.read_text().splitlines(), ["service stop", "service start"])

    def test_default_settings_are_private(self):
        self.assert_switch(self.private)

    def test_override_with_spaces_is_respected(self):
        override = self.base / "private settings/config.json"
        override.parent.mkdir()
        override.write_text(json.dumps(self.original))
        self.env["INIR_CONFIG_DIR"] = str(override.parent)
        original = self.private.read_bytes()
        self.assert_switch(override)
        self.assertEqual(self.private.read_bytes(), original)

    def test_unsafe_paths_are_rejected_before_supervisor_or_write(self):
        alias = self.config / "ii-alias"
        alias.symlink_to(self.ii.parent, target_is_directory=True)
        for path in [self.ii.parent, alias, self.config, self.base, Path("relative"),
                     self.base / "bad\npath"]:
            with self.subTest(path=path):
                self.env["INIR_CONFIG_DIR"] = str(path)
                result = self.run_helper()
                self.assertNotEqual(result.returncode, 0, "unsafe settings override accepted")
                self.assertFalse(self.log.exists(), "unsafe helper stopped the shell")
                self.assertEqual(self.ii.read_bytes(), self.ii_bytes)

    def test_config_file_symlink_into_ii_is_rejected(self):
        self.private.unlink()
        self.private.symlink_to(self.ii)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertTrue(self.private.is_symlink())
        self.assertEqual(self.ii.read_bytes(), self.ii_bytes)

    def test_failed_stop_never_writes_or_starts(self):
        self.env["TEST_STOP_RC"] = "9"
        before = self.private.read_bytes()
        result = self.run_helper()
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(self.private.read_bytes(), before)
        self.assertEqual(self.ii.read_bytes(), self.ii_bytes)
        self.assertEqual(self.log.read_text().splitlines(), ["service stop"])

    def test_failed_restart_is_retried_and_reported(self):
        self.env["TEST_START_RC"] = "9"
        result = self.run_helper()
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertEqual(json.loads(self.private.read_text())["panelFamily"], "waffle")
        self.assertEqual(self.ii.read_bytes(), self.ii_bytes)
        self.assertEqual(self.log.read_text().splitlines(), ["service stop", "service start", "service start"])


if __name__ == "__main__":
    unittest.main()