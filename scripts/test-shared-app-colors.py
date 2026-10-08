#!/usr/bin/env python3
"""Run real palette writers against synthetic app settings, never live files."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
MERGER = ROOT / "scripts/colors/lib/shared-theme-config.py"


class SharedAppColorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-shared-colors-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.generated = self.base / "state/quickshell/user/generated"
        self.generated.mkdir(parents=True)
        self.binary = self.base / "bin"
        self.binary.mkdir()
        self.env = dict(os.environ, HOME=str(self.base), XDG_CONFIG_HOME=str(self.config),
                        XDG_DATA_HOME=str(self.base / "data"), XDG_STATE_HOME=str(self.base / "state"),
                        XDG_CACHE_HOME=str(self.base / "cache"), XDG_RUNTIME_DIR=str(self.base / "runtime"),
                        INIR_CONFIG_DIR=str(self.config / "inir"), INIR_STATE_DIR=str(self.base / "state/inir"),
                        PATH=str(self.binary) + ":" + os.environ["PATH"],
                        MOCK_ACTIONS=str(self.base / "actions.log"))
        self.env.pop("INIR_INSTALL_SHARED_APP_CONFIGS", None)
        self.env.pop("INIR_VENV", None)
        for name in ["pkill", "pgrep", "systemctl", "nautilus", "sudo", "pkexec", "notify-send", "curl"]:
            self.executable(name, '#!/bin/sh\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$MOCK_ACTIONS"\nexit 1\n')
        self.executable("gsettings", '''#!/bin/sh
printf 'gsettings %s\n' "$*" >> "$MOCK_ACTIONS"
[ "$1" = get ] || exit 3
case "$3" in
icon-theme) echo "'Shared Icons'";;
font-name) echo "'Shared Font 11'";;
monospace-font-name) echo "'Shared Mono 12'";;
color-scheme) echo "'prefer-dark'";;
*) echo "'shared'";;
esac
''')
        self.palette = self.generated / "palette.json"
        self.palette.write_text(json.dumps({"term0": "#112233", "term7": "#ccddee", "term15": "#eeeeff",
                                           "primary": "#aabbcc", "on_primary": "#001122", "error": "#ee4455"}))
        self.scss = self.base / "colors.scss"
        self.scss.write_text("$term0: #112233;\n$term7: #ccddee;\n$term15: #eeeeff;\n")

    def executable(self, name, contents):
        path = self.binary / name
        path.write_text(contents)
        path.chmod(0o755)

    def write(self, name, text):
        path = self.config / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_script(self, relative, *arguments):
        return subprocess.run(["bash", str(ROOT / relative), *arguments], env=self.env,
                              capture_output=True, text=True, check=True)

    def terminals(self, *names):
        subprocess.run(["python3", str(ROOT / "scripts/colors/generate_terminal_configs.py"),
                        "--scss", str(self.scss), "--colors", str(self.palette),
                        "--terminal-json", str(self.palette), "--terminals", *names],
                       env=self.env, capture_output=True, text=True, check=True)

    def test_generators_preserve_base_settings_and_update_color_files(self):
        names = ["alacritty/alacritty.toml", "foot/foot.ini", "wezterm/wezterm.lua", "ghostty/config",
                 "btop/btop.conf", "lazygit/config.yml", "yazi/theme.toml", "starship.toml"]
        originals = {self.write(name, f"# personal {name}\nfont = 'sentinel'\n"): None for name in names}
        originals = {p: p.read_bytes() for p in originals}
        for _ in range(2):
            self.terminals("all")
            for path, original in originals.items():
                self.assertEqual(path.read_bytes(), original, str(path))
        for name in ["alacritty/colors.toml", "foot/colors.ini", "wezterm/colors.lua", "ghostty/themes/ii-auto",
                     "btop/themes/ii-auto.theme", "lazygit/ii-theme.yml", "yazi/flavors/ii-auto.yazi/flavor.toml"]:
            self.assertRegex((self.config / name).read_text(), r"112233|aabbcc", name)
        self.assertFalse((self.base / ".config").exists(), "writers must honor XDG_CONFIG_HOME")

    def test_starship_selected_palette_preserves_layout_and_extra_entries(self):
        path = self.write("starship.toml", '''palette='ii'
format = "$directory $character"
[palettes.ii] # selected colors
# personal palette slot
custom = '#123456'
primary = '#000000'
[directory]
style = 'bold primary'
''')
        self.terminals("starship")
        parsed = tomllib.loads(path.read_text())
        self.assertEqual(parsed["palette"], "ii")
        self.assertEqual(parsed["palettes"]["ii"]["primary"], "#aabbcc")
        self.assertEqual(parsed["palettes"]["ii"]["custom"], "#123456")
        self.assertEqual(parsed["format"], "$directory $character")
        self.assertEqual(parsed["directory"]["style"], "bold primary")
        self.assertIn("# personal palette slot", path.read_text())
        for other in ["palette='personal'\n[palettes.ii]\nprimary='#000000'\n",
                      "[directory]\npalette='ii'\n[palettes.ii]\nprimary='#000000'\n"]:
            path.write_text(other)
            self.terminals("starship")
            self.assertEqual(path.read_text(), other)

    def test_fuzzel_preserves_base_config(self):
        path = self.write("fuzzel/fuzzel.ini", '[main]\nfont=Personal Font:size=13\ninclude=personal-theme.ini\n[border]\nwidth=9\n')
        original = path.read_bytes()
        for _ in range(2):
            self.terminals("fuzzel")
            self.assertEqual(path.read_bytes(), original)
            theme = self.config / "fuzzel/fuzzel_theme.ini"
            self.assertTrue(theme.is_file(), "Fuzzel output must honor XDG_CONFIG_HOME")
            self.assertIn("[colors]", theme.read_text())
            self.assertIn("aabbcc", theme.read_text())
            self.assertFalse((self.base / ".config").exists())

    def gtk_fixture(self):
        settings = {}
        for version in (3, 4):
            settings[self.write(f"gtk-{version}.0/settings.ini", "[Settings]\ngtk-font-name=Personal Font 13\ngtk-icon-theme-name=Personal Icons\n")] = None
            target = self.base / f"gtk-{version}-linked.css"
            target.write_text('''/* @define-color accent_color #comment; */
@import url("personal.css");
@define-color accent_color #000000;
:root { --accent-bg-color: #000000; --personal-spacing: 9px; }
@media (prefers-color-scheme: dark) { :root { --accent-bg-color: #000000; } }
window { font-family: 'Personal Font'; padding: 9px; }
label { content: "--accent-bg-color: #example;"; }
''')
            link = self.config / f"gtk-{version}.0/gtk.css"
            link.symlink_to(target)
        settings[self.write("kdeglobals", "[General]\nfont=Personal Font,13\nwidgetStyle=PersonalStyle\nColorScheme=old\n[Icons]\nTheme=Personal Icons\n[Unknown]\nkey=keep\n[Colors:Window]\nBackgroundNormal=0,0,0\n")] = None
        for version in (5, 6):
            settings[self.write(f"qt{version}ct/qt{version}ct.conf", "[Appearance]\nstyle=PersonalStyle\nicon_theme=Personal Icons\ncolor_scheme_path=old\n[Fonts]\ngeneral=Personal Font,13\n[Interface]\ncustom=keep\n")] = None
        return {p: p.read_bytes() for p in settings}

    def test_gtk_qt_color_refresh_preserves_preferences_links_and_processes(self):
        settings = self.gtk_fixture()
        self.write("inir/config.json", '{"appearance":{"iconTheme":"Private Stale Icons"}}')
        for _ in range(2):
            self.run_script("scripts/colors/apply-gtk-theme.sh")
        for path, original in settings.items():
            if path.name == "settings.ini":
                self.assertEqual(path.read_bytes(), original)
            else:
                for line in original.decode().splitlines():
                    if line.startswith(("font=", "widgetStyle=", "Theme=", "style=", "icon_theme=", "general=", "custom=", "key=")):
                        self.assertIn(line, path.read_text())
        self.assertNotIn("color_scheme_path=old", (self.config / "qt6ct/qt6ct.conf").read_text())
        self.assertNotIn("BackgroundNormal=0,0,0", (self.config / "kdeglobals").read_text())
        for version in (3, 4):
            link = self.config / f"gtk-{version}.0/gtk.css"
            self.assertTrue(link.is_symlink())
            css = link.read_text()
            for fragment in ["#comment", '@import url("personal.css");', "padding: 9px", "--personal-spacing: 9px", 'content: "--accent-bg-color: #example;"']:
                self.assertIn(fragment, css)
            self.assertIn("@define-color accent_color #aabbcc;" if version == 3
                          else "--accent-bg-color: #aabbcc;", css)
        actions = (self.base / "actions.log").read_text()
        self.assertNotIn("gsettings set", actions)
        for action in ["nautilus", "systemctl", "pkill"]:
            self.assertNotIn(action, actions)

    def test_disabled_gtk_and_qt_writers_are_respected_independently(self):
        settings = self.gtk_fixture()
        gtk = {p: p.read_bytes() for p in self.config.glob("gtk-*/*")}
        self.write("inir/config.json", '{"appearance":{"wallpaperTheming":{"enableAppsAndShell":false}}}')
        self.run_script("scripts/colors/apply-gtk-theme.sh")
        for path, original in gtk.items():
            self.assertEqual(path.read_bytes(), original)
        for path, original in settings.items():
            path.write_bytes(original)
        self.write("inir/config.json", '{"appearance":{"wallpaperTheming":{"enableQtApps":false}}}')
        self.run_script("scripts/colors/apply-gtk-theme.sh")
        for path, original in settings.items():
            if path.name == "kdeglobals" or path.name.startswith("qt"):
                self.assertEqual(path.read_bytes(), original)

    def test_merge_duplicate_keys_missing_sections_and_file_permissions(self):
        path = self.write("qt.conf", "[Appearance]\nstyle=Custom\ncustom_palette=false\ncustom_palette=false\n[Fonts]\nfont=Keep")
        path.chmod(0o600)
        result = subprocess.run(["python3", str(MERGER), "qt", str(path)], env=self.env, text=True,
                                input="[Appearance]\ncustom_palette=true\ncolor_scheme_path=new\nstyle=DoNotUse\n", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_text().count("custom_palette=true"), 2)
        self.assertIn("color_scheme_path=new\n[Fonts]", path.read_text())
        self.assertTrue(path.read_text().endswith("font=Keep"))

    def test_css_write_failure_stops_the_application_step(self):
        self.gtk_fixture()
        path = self.config / "gtk-3.0/gtk.css"
        path.unlink()
        path.symlink_to(self.base)  # A directory cannot be used as a stylesheet.
        result = subprocess.run(["bash", str(ROOT / "scripts/colors/apply-gtk-theme.sh")],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Cannot merge shared colors", result.stderr)
        self.assertTrue(path.is_symlink())

    def test_template_paths_stage_legacy_gtk_outputs_and_honor_xdg(self):
        script = '''import json, sys
sys.path.insert(0, sys.argv[1])
from lib.paths import theme_template_output
print(json.dumps([str(theme_template_output(p)) for p in sys.argv[2:]]))
'''
        inputs = ["~/.config/gtk-3.0/gtk.css", str(self.config / "gtk-4.0/gtk.css"),
                  "~/.local/state/quickshell/user/generated/gtk-4-rendered.css", "~/.config/fuzzel/fuzzel_theme.ini"]
        output = subprocess.check_output(["python3", "-c", script, str(ROOT / "scripts"), *inputs], env=self.env, text=True)
        self.assertEqual(json.loads(output), [str(self.generated / "gtk-3-rendered.css"),
                                             str(self.generated / "gtk-4-rendered.css"),
                                             str(self.generated / "gtk-4-rendered.css"),
                                             str(self.config / "fuzzel/fuzzel_theme.ini")])

    def chrome_call(self, directory):
        self.browser_module("40-chrome.sh", 'write_policy "$2" "#aabbcc"', directory)

    def browser_module(self, name, command, *arguments):
        # Load production definitions, then replace discovery with fixture paths.
        # Never let the real installed-browser registry reach /etc in a test.
        source = (ROOT / "scripts/colors/modules" / name).read_text().split('\nmain "$@"', 1)[0]
        source = source.replace('source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/module-runtime.sh"',
                                'source "$1/scripts/colors/lib/module-runtime.sh"')
        subprocess.run(["bash", "-euc", source + "\n" + command, "fixture", str(ROOT), *map(str, arguments)],
                       env=self.env, check=True, capture_output=True, text=True)

    def test_chrome_updates_only_color_and_preserves_invalid_policy(self):
        directory = self.base / "policies"
        directory.mkdir()
        policy = directory / "ii-theme.json"
        original = {"BackgroundModeEnabled": True, "UnrelatedPolicy": ["sentinel"], "BrowserThemeColor": "#000000"}
        policy.write_text(json.dumps(original))
        self.chrome_call(directory)
        expected = dict(original, BrowserThemeColor="#aabbcc")
        self.assertEqual(json.loads(policy.read_text()), expected)
        written = policy.read_bytes()
        modified = policy.stat().st_mtime_ns
        self.chrome_call(directory)
        self.assertEqual(policy.read_bytes(), written)
        self.assertEqual(policy.stat().st_mtime_ns, modified, "unchanged policies must not trigger reloads")
        policy.write_text("{invalid policy}")
        self.chrome_call(directory)
        self.assertEqual(policy.read_text(), "{invalid policy}")
        policy.unlink()
        self.chrome_call(directory)
        self.assertEqual(json.loads(policy.read_text()), {"BrowserThemeColor": "#aabbcc"})
        self.assertFalse((self.base / "browser").exists())
        self.assertFalse((self.base / "actions.log").exists(), "policy writes must not launch browsers or request elevation")

    def test_chrome_missing_directories_invalid_colors_and_policy_links_are_preserved(self):
        missing = self.base / "missing-policies"
        self.chrome_call(missing)
        self.assertFalse(missing.exists())
        directory = self.base / "policies"
        directory.mkdir()
        target = self.write("chromium/Default/Preferences", '{"personal":"keep"}')
        policy = directory / "ii-theme.json"
        policy.symlink_to(target)
        self.chrome_call(directory)
        self.assertTrue(policy.is_symlink())
        self.assertEqual(target.read_text(), '{"personal":"keep"}')
        self.browser_module("40-chrome.sh", 'write_policy "$2" "invalid" || test "$?" -eq 1', directory)
        self.assertEqual(target.read_text(), '{"personal":"keep"}')
        self.assertFalse((self.base / "actions.log").exists())

    def test_chrome_module_preserves_profiles_disabled_policies_and_permissions(self):
        directory = self.base / "policies"
        directory.mkdir(mode=0o750)
        policy = directory / "ii-theme.json"
        policy.write_text('{"BackgroundModeEnabled":true,"UnrelatedPolicy":"keep"}')
        policy.chmod(0o600)
        prefs = self.write("chromium/Default/Preferences", '{"browser":{"theme":{"color_scheme":0}},"personal":"keep"}')
        original = prefs.read_bytes()
        self.env["INIR_INSTALL_SHARED_APP_CONFIGS"] = "true"
        (self.generated / "app-palette.json").write_text('{"app_headerbar_bg":"#112233"}')
        command = '''fixture_dir="$2" fixture_data="$3"
installed_chromium_browsers() { printf '%s|%s|fixture-browser\\n' "$fixture_dir" "$fixture_data"; }
main
'''
        self.browser_module("40-chrome.sh", command, directory, prefs.parent.parent)
        self.assertEqual(prefs.read_bytes(), original)
        self.assertEqual(json.loads(policy.read_text()), {"BackgroundModeEnabled": True, "UnrelatedPolicy": "keep", "BrowserThemeColor": "#112233"})
        self.assertEqual(policy.stat().st_mode & 0o777, 0o600)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o750)
        self.write("inir/config.json", '{"appearance":{"wallpaperTheming":{"enableChrome":false}}}')
        original_policy = policy.read_bytes()
        self.browser_module("40-chrome.sh", command, directory, prefs.parent.parent)
        self.assertEqual(policy.read_bytes(), original_policy)
        self.assertEqual(prefs.read_bytes(), original)
        self.assertFalse((self.base / "actions.log").exists())

    def test_firefox_generates_colors_without_touching_any_profile(self):
        profile = self.write("mozilla/firefox/personal.default/user.js", 'user_pref("personal", true);\n')
        self.write("mozilla/firefox/profiles.ini", '[Profile0]\nPath=personal.default\nIsRelative=1\n')
        # Also preserve profiles that do not yet have user.js, and absolute paths.
        other = self.base / "absolute-profile"
        other.mkdir()
        with (self.config / "mozilla/firefox/profiles.ini").open("a") as ini:
            ini.write(f'[Profile1]\nPath={other}\nIsRelative=0\n')
        original = profile.read_bytes()
        palette = dict.fromkeys(["app_headerbar_bg", "app_surface_popup", "app_foreground", "app_subtext",
                                "app_on_surface_popup", "app_selection", "app_on_selection", "app_accent",
                                "app_on_accent", "app_border_subtle"], "#aabbcc")
        (self.generated / "app-palette.json").write_text(json.dumps(palette))
        self.env["INIR_INSTALL_SHARED_APP_CONFIGS"] = "true"
        snippet = self.generated / "firefox-colors.js"
        written = b""
        for enabled in (True, False):
            self.write("inir/config.json", json.dumps({"appearance": {"wallpaperTheming": {"enableFirefox": enabled}}}))
            self.run_script("scripts/colors/modules/45-firefox.sh")
            self.assertEqual(profile.read_bytes(), original)
            self.assertFalse((other / "user.js").exists())
            if enabled:
                self.assertIn('user_pref("ui.accentcolor", "#aabbcc")', snippet.read_text())
                written = snippet.read_bytes()
            else:
                self.assertEqual(snippet.read_bytes(), written)

    def test_firefox_invalid_palette_preserves_last_generated_output(self):
        snippet = self.generated / "firefox-colors.js"
        snippet.write_text("last valid generated colours\n")
        (self.generated / "app-palette.json").write_text('{"app_headerbar_bg":"bad colour"}')
        self.run_script("scripts/colors/modules/45-firefox.sh")
        self.assertEqual(snippet.read_text(), "last valid generated colours\n")

    def test_pear_refresh_does_not_select_a_theme_or_enable_debugging(self):
        self.executable("pear-desktop", '#!/bin/sh\n# wrapper reads pear-flags.conf\nexit 1\n')
        config = self.write("YouTube Music/config.json", '{"options":{"themes":["personal.css"]},"unrelated":"keep"}')
        original = config.read_bytes()
        self.run_script("scripts/colors/modules/80-pear-desktop.sh")
        self.assertEqual(config.read_bytes(), original)
        css = self.generated / "pear-desktop-theme.css"
        self.assertIn("#aabbcc", css.read_text())
        self.assertFalse((self.config / "pear-flags.conf").exists())
        config.write_text(json.dumps({"options": {"themes": [str(css), "personal.css"]}}))
        original = config.read_bytes()
        self.run_script("scripts/colors/modules/80-pear-desktop.sh")
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((self.config / "pear-flags.conf").exists())

    def test_vscode_colors_preserve_editor_settings_and_invalid_registry(self):
        # Import the production writer in a child process with temporary HOME.
        script = '''import sys
sys.path.insert(0, sys.argv[1])
from vscode.theme_generator import generate_vscode_theme, strip_vscode_theme
assert generate_vscode_theme(*sys.argv[2:], fork_key="code")
assert strip_vscode_theme(sys.argv[4])
'''
        settings = self.write("Code/User/settings.json", '{"editor.fontFamily":"Personal Font","workbench.colorTheme":"Personal","workbench.colorCustomizations":{"foreground":"#123456"}}')
        original = settings.read_bytes()
        registry = self.base / ".vscode/extensions/extensions.json"
        registry.parent.mkdir(parents=True)
        registry.write_text("{invalid registry}")
        subprocess.run(["python3", "-c", script, str(ROOT / "scripts/colors"), str(self.palette), str(self.scss), str(settings)],
                       env=self.env, check=True, capture_output=True, text=True)
        self.assertEqual(settings.read_bytes(), original)
        self.assertEqual(registry.read_text(), "{invalid registry}")
        self.assertTrue(list(registry.parent.glob("*/themes/*.json")))

    def test_editor_module_keeps_personal_neovim_and_respects_disabled_fork(self):
        plugin = self.write("nvim/lua/plugins/neovim.lua", 'return {{"bjarneo/aether.nvim", opts = {personal = true}}}\n')
        settings = self.write("Code/User/settings.json", '{"workbench.colorTheme":"Personal","workbench.colorCustomizations":{"foreground":"#123456"}}')
        self.write("inir/config.json", '{"appearance":{"wallpaperTheming":{"vscodeEditors":{"code":false}}}}')
        (self.generated / "material_colors.scss").write_bytes(self.scss.read_bytes())
        self.executable("go", '#!/bin/sh\nexit 1\n')  # Exercise the real Python fallback.
        original_plugin, original_settings = plugin.read_bytes(), settings.read_bytes()
        self.run_script("scripts/colors/modules/30-editors.sh")
        self.assertEqual(plugin.read_bytes(), original_plugin)
        self.assertEqual(settings.read_bytes(), original_settings)
        self.assertFalse((self.base / ".vscode/extensions/inir-material-theme").exists())


if __name__ == "__main__":
    unittest.main()
