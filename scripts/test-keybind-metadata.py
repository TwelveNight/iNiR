#!/usr/bin/env python3
"""Regression coverage for native labels and shared shortcut categorization."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metadata = load("metadata", "niri-config.py")
cheatsheet = load("cheatsheet", "parse_niri_keybinds.py")


class MetadataTests(unittest.TestCase):
    def test_action_categories_ignore_localized_labels(self):
        examples = [
            ('spawn "/home/night/.local/bin/inir" "region" "menu"', "Screenshots"),
            ('spawn "inir" "region" "recordWithSound"', "Screenshots"),
            ('spawn "inir" "equalizer" "toggle"', "Media"),
            ('spawn "/usr/bin/kitty" "--title" "btop" "/usr/bin/btop"', "Applications"),
            ('spawn "systemctl" "suspend"', "System"),
            ('set-window-width "-30"', "Resize"),
            ('move-window-to-workspace-down', "Workspaces"),
            ('move-window-to-workspace-up focus=false', "Workspaces"),
            ('next-window scope="app-id"', "Window Switcher"),
        ]
        for action, category in examples:
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "binds.kdl"
                path.write_text('binds {\n Mod+T hotkey-overlay-title="自定义说明" { ' + action + '; }\n}\n')
                row = metadata._read_bind_entries(path)[0]
                self.assertEqual(row["description"], "自定义说明")
                self.assertEqual(row["category"], category)
                self.assertEqual(cheatsheet.categorize_keybind({"action": action, "comment": "自定义说明"}), category)

    def test_native_title_and_shell_substitution_survive_editor_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            shutil.copytree(ROOT / "defaults/niri", Path(directory) / "niri")
            personal = Path(directory) / "niri/config.d/75-personal-binds.kdl"
            stock = Path(directory) / "niri/config.d/70-binds.kdl"
            before = stock.read_bytes()
            title = '编辑 "个人" 快捷键'
            script = 'xdg-open "${XDG_CONFIG_HOME:-$HOME/.config}/niri/config.d/75-personal-binds.kdl"'
            action = 'spawn "bash" "-c" ' + json.dumps(script)
            options = 'repeat=false hotkey-overlay-title=' + json.dumps(title, ensure_ascii=False)
            personal.write_text('binds {\n Mod+T ' + options + ' { ' + action + '; }\n}\n')
            row = metadata._read_bind_entries(personal)[0]
            self.assertEqual(row["action"], action)
            self.assertEqual(row["description"], title)
            self.assertEqual(row["category"], "iNiR Shell")
            legacy = cheatsheet.parse_keybinds_from_block(personal.read_text().split('\n', 1)[1])[0]
            self.assertEqual(legacy["action"], action)
            self.assertEqual(legacy["comment"], title)
            result = subprocess.run([
                "python3", str(ROOT / "scripts/niri-config.py"), "set-bind", row["key_combo"],
                row["action"], "--options", row["options"],
            ], env=dict(os.environ, XDG_CONFIG_HOME=directory), capture_output=True, text=True, check=True)
            self.assertTrue(json.loads(result.stdout)["success"])
            saved = metadata._read_bind_entries(personal)[0]
            self.assertEqual(saved["description"], title)
            self.assertEqual(saved["action"], action)
            self.assertEqual(stock.read_bytes(), before)

    def test_personal_wrappers_are_parsed_completely_and_consistently(self):
        path = ROOT / "defaults/niri/config.d/75-personal-binds.kdl"
        rows = metadata._read_bind_entries(path)
        # Stop at the top-level block boundary; recent-windows has its own binds.
        blocks, _ = cheatsheet.find_all_binds_blocks(path.read_text())
        legacy = cheatsheet.parse_keybinds_from_block(blocks[0])
        self.assertEqual(len(rows), len(legacy))
        for row, old in zip(rows, legacy):
            with self.subTest(key=row["key_combo"]):
                self.assertEqual(row["action"], old["action"])
                self.assertEqual(row["description"], old["comment"])
                self.assertEqual(row["category"], cheatsheet.categorize_keybind(old))
                self.assertNotEqual(row["category"], "Other")
        by_key = {row["key_combo"]: row for row in rows}
        self.assertEqual(by_key["Super+W"]["category"], "Window Management")
        self.assertEqual(by_key["Ctrl+Shift+A"]["category"], "Applications")
        self.assertEqual(by_key["Mod+Ctrl+Shift+N"]["category"], "Workspaces")
        self.assertEqual(by_key["Mod+D"]["options"], "repeat=false hotkey-overlay-title=null")


if __name__ == "__main__":
    unittest.main()
