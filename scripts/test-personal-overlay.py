#!/usr/bin/env python3
"""Exercise personal-overlay boundaries in temporary trees, with no live writes."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PersonalOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-overlay-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.state = self.base / "state"
        self.ii = self.config / "illogical-impulse"
        self.inir = self.config / "inir"
        self.ii.mkdir(parents=True)
        self.inir.mkdir()
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.config),
                        XDG_STATE_HOME=str(self.state), XDG_CACHE_HOME=str(self.base / "cache"),
                        XDG_DATA_HOME=str(self.base / "data"), XDG_BIN_HOME=str(self.base / "bin"))
        self.env.pop("INIR_CONFIG_DIR", None)
        self.env.pop("INIR_STATE_DIR", None)
        self.env.pop("INIR_VENV", None)
        self.env["REPO_ROOT"] = str(ROOT)

    def bash(self, script):
        return subprocess.run(["bash", "-euc", script], env=self.env,
                              capture_output=True, text=True, check=True).stdout

    def test_runtime_helpers_agree_with_and_without_xdg_runtime(self):
        self.env["PYTHONPATH"] = str(ROOT / "scripts")
        for runtime in [str(self.base / "runtime with spaces"), ""]:
            self.env["XDG_RUNTIME_DIR"] = runtime
            shell = self.bash(f'source "{ROOT}/scripts/lib/config-path.sh"; inir_temp_dir').strip()
            python = subprocess.run(["python3", "-c", "from lib.paths import temp_dir; print(temp_dir())"],
                                    env=self.env, text=True, capture_output=True, check=True).stdout.strip()
            expected = Path(runtime) / "inir" if runtime else self.base / "cache/inir/tmp"
            self.assertEqual(shell, str(expected))
            self.assertEqual(python, shell)

    def test_update_backup_pruning_never_touches_shared_backups(self):
        shared = self.state / "quickshell/backups"
        for i in range(8):
            backup = shared / f"pre-update-{i}"
            backup.mkdir(parents=True)
            (backup / "II-sentinel").write_text("keep")
        target = self.config / "quickshell/inir"
        target.mkdir(parents=True)
        (target / "shell.qml").write_text("fixture")
        self.env["INIR_STATE_DIR"] = str(self.state / "custom private state")
        private = Path(self.env["INIR_STATE_DIR"]) / "backups"
        for i in range(8):
            (private / f"pre-update-{i}").mkdir(parents=True)
        output = self.bash(f'''source "{ROOT}/sdata/lib/robust-update.sh"
create_update_backup "$II_TARGET"
''').strip()
        self.assertEqual(Path(output).parent, private)
        self.assertEqual((Path(output) / "shell.qml").read_text(), "fixture")
        self.assertEqual(len(list(private.glob("pre-update-*"))), 5)
        self.assertEqual(len(list(shared.glob("*/II-sentinel"))), 8)

    def test_no_runtime_files_in_ii_temp_namespace(self):
        for directory in ["modules", "services", "scripts"]:
            for path in (ROOT / directory).rglob("*"):
                if path.suffix not in {".qml", ".sh", ".py"} or path.name.startswith("test-"):
                    continue
                content = path.read_text()
                self.assertNotIn("/tmp/quickshell/", content, str(path))
                self.assertNotIn("/tmp/qs-ytmusic-mpv.sock", content, str(path))

    def test_ii_marker_never_marks_inir_installed(self):
        (self.ii / "installed_true").touch()
        output = self.bash(f'''
source "{ROOT}/sdata/lib/environment-variables.sh"
source "{ROOT}/scripts/lib/config-path.sh"
printf '%s\\n' "$FIRSTRUN_FILE" "$(inir_config_file)" "$(inir_state_dir)"
test ! -f "$FIRSTRUN_FILE"
''').splitlines()
        self.assertEqual(output, [str(self.inir / "installed_true"),
                                 str(self.inir / "config.json"), str(self.state / "inir")])
        self.assertTrue((self.ii / "installed_true").exists())

    def test_migrations_only_change_inir_config(self):
        value = {"language": {"ui": "es_AR"}, "appearance": {"cava": {"allowedApps": ["game"]}}}
        for folder in [self.ii, self.inir]:
            (folder / "config.json").write_text(json.dumps(value))
        original = (self.ii / "config.json").read_bytes()
        self.bash(f'''
source "{ROOT}/sdata/migrations/041-visualizer-app-filter-semantics.sh"
migration_apply
source "{ROOT}/sdata/migrations/043-spanish-catalogue-es-419.sh"
migration_apply
source "{ROOT}/sdata/migrations/019-config-dir-rename-compat.sh"
migration_apply
''')
        self.assertEqual((self.ii / "config.json").read_bytes(), original)
        self.assertFalse(self.ii.is_symlink())
        current = json.loads((self.inir / "config.json").read_text())
        self.assertEqual(current["language"]["ui"], "es_419")
        self.assertEqual(current["appearance"]["cava"], {"blockedApps": ["game"]})

    def test_version_does_not_fall_back_to_ii_runtime(self):
        runtime = self.config / "quickshell/ii"
        runtime.mkdir(parents=True)
        (runtime / "shell.qml").write_text("II sentinel")
        (self.ii / "version.json").write_text('{"version":"II"}')
        output = self.bash(f'''
source "{ROOT}/sdata/lib/versioning.sh"
printf '%s\\n' "$VERSION_FILE_LOCAL"
test -z "$(get_runtime_shell_dir)"
''')
        self.assertEqual(output.strip(), str(self.inir / "version.json"))

    def test_state_initialization_keeps_ii_data(self):
        shared = self.state / "quickshell/user"
        shared.mkdir(parents=True)
        (shared / "todo.json").write_text('["II todo"]')
        cache = self.base / "cache/quickshell/notifications"
        cache.mkdir(parents=True)
        (cache / "notifications.json").write_text('["II notification"]')
        stage = (ROOT / "sdata/subcmd-install/3.files.sh").read_text()
        initial = stage.split("# Determine first run", 1)[0]
        script = self.base / "initial.sh"
        script.write_text(initial)
        self.bash(f'''
source "{ROOT}/sdata/lib/environment-variables.sh"
quiet=true
v() {{ "$@"; }}
source "{script}"
''')
        self.assertEqual((shared / "todo.json").read_text(), '["II todo"]')
        self.assertEqual((cache / "notifications.json").read_text(), '["II notification"]')
        self.assertEqual(json.loads((self.state / "inir/user/todo.json").read_text()), [])

    def test_shared_theme_inputs_are_private_and_outputs_shared(self):
        manifest = json.loads((ROOT / "defaults/matugen/templates.json").read_text())
        outputs = [entry["output"] for entry in manifest["templates"]]
        self.assertIn("~/.local/state/quickshell/user/generated/color.txt", outputs)
        self.assertIn("~/.local/state/quickshell/user/generated/gtk-4-rendered.css", outputs)
        self.assertNotIn("~/.config/gtk-4.0/gtk.css", outputs)
        # Execute the actual resolver used by the production colour modules.
        output = self.bash(f'''
source "{ROOT}/scripts/colors/lib/module-runtime.sh"
printf '%s\\n' "$CONFIG_FILE" "$STATE_DIR"
''').splitlines()
        self.assertEqual(output, [str(self.inir / "config.json"), str(self.state / "quickshell")])

    def test_python_settings_override_does_not_adopt_ii(self):
        self.env["INIR_CONFIG_DIR"] = str(self.base / "private settings")
        self.env["PYTHONPATH"] = str(ROOT / "scripts")
        result = subprocess.run(["python3", "-c", "from lib.paths import config_dir; print(config_dir())"],
                                env=self.env, check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), self.env["INIR_CONFIG_DIR"])

    def test_niri_session_imports_environment_without_switching_dm(self):
        binary = self.base / "mock-bin"
        binary.mkdir()
        log = self.base / "systemctl.log"
        systemctl = binary / "systemctl"
        systemctl.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_SYSTEMCTL_LOG"\n')
        systemctl.chmod(0o755)
        listener = self.config / "quickshell/ii/scripts/colors/skwd-wall-theme-listener.sh"
        listener.parent.mkdir(parents=True)
        listener.write_text("#!/bin/sh\n")
        listener.chmod(0o755)
        self.env.update(PATH=str(binary) + ":" + self.env["PATH"],
                        MOCK_SYSTEMCTL_LOG=str(log), NIRI_SOCKET="fixture", WAYLAND_DISPLAY="fixture-wayland",
                        XDG_CURRENT_DESKTOP="niri")
        subprocess.run(["bash", str(ROOT / "scripts/wallpaper/skwd-session.sh")], env=self.env, check=True)
        self.assertEqual(log.read_text().splitlines(), [
            "--user import-environment WAYLAND_DISPLAY NIRI_SOCKET XDG_CURRENT_DESKTOP",
            "--user restart skwd-walld.service", "--user start ii-skwd-wall-theme.service"])
        self.env.pop("NIRI_SOCKET")
        result = subprocess.run(["bash", str(ROOT / "scripts/wallpaper/skwd-session.sh")],
                                env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(log.read_text().splitlines()), 3)

    def test_real_skewd_state_and_command_logic(self):
        source = (ROOT / "services/skwdState.js").read_text().replace(".pragma library", "")
        runner = self.base / "state-test.cjs"
        runner.write_text(source + '''
const assert = require('node:assert/strict');
const state = {outputs: [
  {name:'unplugged', connected:false, path:'/stale.png'},
  {name:'eDP-2', connected:true, type:'video', path:'/A wallpaper $x.mp4'},
  {name:'HDMI-A-1', connected:true, type:'we', we_id:'123'}
]};
assert.equal(wallpaperPath(state, 'eDP-2', '/cache'), '/A wallpaper $x.mp4');
assert.equal(wallpaperPath(state, 'HDMI-A-1', '/cache'), '/cache/skwd-wall-v2/we-thumbs/123.webp');
assert.equal(wallpaperPath({}, '', '/cache'), '');
assert.deepEqual(applyCommand('/A wallpaper $x.mp4', 'eDP-2'),
  ['skwd-helm','apply','/A wallpaper $x.mp4','-o','eDP-2']);
assert.equal(wallpaperPath({outputs:{'DP-1':{path:'/other.png'}}}, 'DP-1','/cache'), '/other.png');
''')
        subprocess.run(["node", str(runner)], check=True)

    def test_install_helpers_preserve_existing_app_settings(self):
        self.env["HOME"] = str(self.base)
        self.env.pop("INIR_VENV", None)
        self.env.pop("INIR_INSTALL_SHARED_APP_CONFIGS", None)
        self.env.pop("INIR_INSTALL_SHELL_PROFILES", None)
        gtk = self.base / ".config/gtk-3.0/settings.ini"
        gtk.parent.mkdir(parents=True)
        gtk.write_text("personal GTK settings")
        profile = self.base / ".bashrc"
        profile.write_text("personal profile")
        self.bash(f'''
source "{ROOT}/sdata/lib/package-installers.sh"
source "{ROOT}/sdata/lib/functions.sh"
log_info() {{ :; }}
for app in gtk kvantum environment foot kitty fish bash zsh; do
    "setup-$app-config"
done
ensure_launcher_path_in_shells "$XDG_BIN_HOME"
''')
        self.assertEqual(gtk.read_text(), "personal GTK settings")
        self.assertEqual(profile.read_text(), "personal profile")
        self.assertFalse((self.base / ".config/environment.d").exists())
        self.assertFalse((self.base / ".config/kitty").exists())

    def test_uninstall_preserves_ii_shared_state_and_themes(self):
        shared = self.state / "quickshell/user"
        shared.mkdir(parents=True)
        sentinel = shared / "todo.json"
        sentinel.write_text("II todo")
        palette = shared / "generated/colors.json"
        palette.parent.mkdir()
        palette.write_text("shared palette")
        kitty = self.config / "kitty"
        kitty.mkdir()
        (kitty / "kitty.conf").write_text("current settings")
        (kitty / "kitty.conf.old").write_text("stale unrelated backup")
        ii_runtime = self.config / "quickshell/ii"
        ii_runtime.mkdir(parents=True)
        (ii_runtime / "shell.qml").write_text("II")
        own_state = self.state / "inir/user"
        own_state.mkdir(parents=True)
        (own_state / "todo.json").write_text("iNiR")
        self.bash(f'''
source "{ROOT}/sdata/lib/uninstall.sh"
tui_info() {{ :; }}
tui_success() {{ :; }}
STY_FAINT= STY_RST= STY_RED=
ask=false
has_other_quickshell_configs
uninstall_remove_inir_only
uninstall_restore_preinstall_configs
uninstall_handle_shared_configs
uninstall_handle_quickshell_shared
''')
        self.assertFalse(own_state.exists())
        self.assertEqual(sentinel.read_text(), "II todo")
        self.assertEqual(palette.read_text(), "shared palette")
        self.assertEqual((kitty / "kitty.conf").read_text(), "current settings")

    def test_switchwall_dispatch_writes_only_after_success(self):
        config = self.inir / "config.json"
        config.write_text(json.dumps({"background": {"wallpaperPath": "/previous.png"}}))
        binary = self.base / "mock-bin"
        binary.mkdir()
        mock = binary / "skwd-helm"
        mock.write_text('#!/bin/sh\n[ "$2" != /fail.png ] || exit 7\nprintf "%s\\n" "$@" > "$MOCK_APPLY_LOG"\n')
        mock.chmod(0o755)
        self.env.update(PATH=str(binary) + ":" + self.env["PATH"],
                        MOCK_APPLY_LOG=str(self.base / "apply.log"))
        script = ROOT / "scripts/colors/switchwall.sh"
        failed = subprocess.run(["bash", str(script), "--image", "/fail.png"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 7, failed.stderr)
        self.assertEqual(json.loads(config.read_text())["background"]["wallpaperPath"], "/previous.png")
        path = "/a wallpaper $x.png"
        subprocess.run(["bash", str(script), "--image", path], env=self.env, check=True, capture_output=True)
        self.assertEqual((self.base / "apply.log").read_text().splitlines(), ["apply", path])
        self.assertEqual(json.loads(config.read_text())["background"]["wallpaperPath"], path)

    def test_python_installer_never_recreates_ii_environment(self):
        shared = self.state / "quickshell/.venv"
        shared.mkdir(parents=True)
        sentinel = shared / "II-sentinel"
        sentinel.write_text("II dependencies")
        binary = self.base / "mock-bin"
        binary.mkdir()
        mock = binary / "uv"
        mock.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$MOCK_UV_LOG"\nexit 1\n')
        mock.chmod(0o755)
        self.env.update(PATH=str(binary) + ":" + self.env["PATH"],
                        MOCK_UV_LOG=str(self.base / "uv.log"))
        self.bash(f'''
source "{ROOT}/sdata/lib/environment-variables.sh"
source "{ROOT}/sdata/lib/package-installers.sh"
tui_info() {{ :; }}
log_warning() {{ :; }}
x() {{ "$@"; }}
install-python-packages
''')
        self.assertIn(str(self.state / "inir/.venv"), (self.base / "uv.log").read_text())
        self.assertEqual(sentinel.read_text(), "II dependencies")

    def test_personal_installer_snapshots_before_deployment(self):
        fixture = self.base / "fixture"
        entry = fixture / "scripts/personal/install.sh"
        entry.parent.mkdir(parents=True)
        helper = fixture / "scripts/lib/private_paths.py"
        helper.parent.mkdir(parents=True)
        helper.write_text((ROOT / "scripts/lib/private_paths.py").read_text())
        for name in ["install.sh", "preflight.sh", "configure-session.py", "dependencies.py"]:
            dest = entry.with_name(name)
            dest.write_text((ROOT / "scripts/personal" / name).read_text())
            dest.chmod(0o755)
        setup = fixture / "setup"
        setup.write_text('''#!/bin/sh
printf "%s\\n" "$@" > "$MOCK_SETUP_LOG"
printf 'environment {}\\n' > "$XDG_CONFIG_HOME/niri/config.kdl"
touch "$INIR_CONFIG_DIR/installed_true"
mkdir -p "$XDG_BIN_HOME" "$INIR_VENV/bin" "$XDG_CONFIG_HOME/systemd/user/niri.service.wants"
printf '#!/bin/sh\\nexit 0\\n' > "$XDG_BIN_HOME/inir"
printf '#!/bin/sh\\nexit 0\\n' > "$INIR_VENV/bin/python3"
chmod +x "$XDG_BIN_HOME/inir" "$INIR_VENV/bin/python3"
ln -s ../inir.service "$XDG_CONFIG_HOME/systemd/user/niri.service.wants/inir.service"
''')
        setup.chmod(0o755)
        niri = self.config / "niri/config.kdl"
        niri.parent.mkdir()
        niri.write_text("previous niri")
        old_wants = self.config / "systemd/user/default.target.wants/inir.service"
        old_wants.parent.mkdir(parents=True)
        old_wants.symlink_to("../inir.service")
        desktop = Path(self.env["XDG_DATA_HOME"]) / "applications/inir.desktop"
        desktop.parent.mkdir(parents=True)
        desktop.write_text("previous desktop entry")
        listener = self.config / "quickshell/ii/scripts/colors/skwd-wall-theme-listener.sh"
        listener.parent.mkdir(parents=True)
        listener.write_text("#!/bin/sh\n")
        listener.chmod(0o755)
        self.env["INIR_CONFIG_DIR"] = str(self.base / "private settings")
        private = Path(self.env["INIR_CONFIG_DIR"])
        private.mkdir()
        (private / "config.json").write_text("private config")
        (self.ii / "installed_true").touch()
        binary = self.base / "mock-bin"
        binary.mkdir()
        for name in ["skwd-helm", "niri", "qs", "jq", "rsync", "uv", "systemctl", "swayidle", "swaylock"]:
            mock = binary / name
            mock.write_text("#!/bin/sh\nexit 0\n")
            mock.chmod(0o755)
        self.env.update(PATH=str(binary) + ":" + self.env["PATH"],
                        MOCK_SETUP_LOG=str(self.base / "setup.log"))
        subprocess.run(["bash", str(entry), "--check"], env=self.env,
                       check=True, capture_output=True, text=True)
        self.assertFalse((self.state / "inir/install-backups").exists())
        self.assertEqual(niri.read_text(), "previous niri")
        # A failed preflight must stop before backups or setup starts.
        (binary / "systemctl").write_text("#!/bin/sh\nexit 1\n")
        failed = subprocess.run(["bash", str(entry), "--quiet"], env=self.env, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.state / "inir/install-backups").exists())
        self.assertFalse((self.base / "setup.log").exists())
        (binary / "systemctl").write_text("#!/bin/sh\nexit 0\n")
        subprocess.run(["bash", str(entry), "--quiet"], env=self.env,
                       check=True, capture_output=True, text=True)
        snapshots = list((self.state / "inir/install-backups").iterdir())
        self.assertEqual(len(snapshots), 1)
        self.assertEqual((snapshots[0] / "config/niri/config.kdl").read_text(), "previous niri")
        self.assertEqual((snapshots[0] / "inir-config/config.json").read_text(), "private config")
        self.assertEqual((snapshots[0] / "config/systemd/user/default.target.wants/inir.service").readlink(),
                         Path("../inir.service"))
        self.assertEqual((snapshots[0] / "data/applications/inir.desktop").read_text(), "previous desktop entry")
        self.assertIn(str(private), niri.read_text())
        self.assertNotIn("$HOME", niri.read_text())
        self.assertTrue((self.ii / "installed_true").exists())
        self.assertEqual((self.base / "setup.log").read_text().splitlines(),
                         ["install", "--skip-deps", "--skip-setups", "--quiet"])

    def test_cliphist_shares_the_native_database(self):
        # Both commands use only temporary XDG roots; never the live clipboard.
        subprocess.run(["cliphist", "store"], input="II clipboard sentinel", text=True,
                       check=True, env=self.env)
        wrapper = str(ROOT / "scripts/cliphist-inir.sh")
        subprocess.run([wrapper, "store"], input="iNiR clipboard sentinel", text=True,
                       env=self.env, check=True)
        result = subprocess.check_output([wrapper, "list"], text=True, env=self.env)
        self.assertIn("iNiR clipboard sentinel", result)
        self.assertIn("II clipboard sentinel", result)
        self.assertEqual(result, subprocess.check_output(["cliphist", "list"], text=True, env=self.env))
        subprocess.run([wrapper, "wipe"], env=self.env, check=True)
        self.assertEqual(subprocess.check_output(["cliphist", "list"], text=True, env=self.env), "")
        self.assertFalse((self.state / "inir/cliphist").exists())

    def test_session_paths_are_concrete_and_niri_config_valid(self):
        import importlib.util
        import shutil
        spec = importlib.util.spec_from_file_location("session_config", ROOT / "scripts/personal/configure-session.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        shutil.copytree(ROOT / "defaults/niri", self.config / "niri")
        args = (self.config, self.inir, self.state / "private state", self.state / "private state/.venv", self.base / "bin dir")
        module.configure(*args)
        env_file = self.config / "niri/config.d/40-environment.kdl"
        first = env_file.read_text()
        module.configure(*args)
        self.assertEqual(first, env_file.read_text())
        self.assertNotIn("$HOME", first)
        binds = (self.config / "niri/config.d/70-binds.kdl").read_text()
        self.assertNotIn('spawn "inir"', binds)
        self.assertIn(str(self.base / "bin dir/inir"), binds)
        subprocess.run(["niri", "validate", "--config", str(self.config / "niri/config.kdl")],
                       check=True, capture_output=True)
        dropin = (self.config / "systemd/user/inir.service.d/20-personal-paths.conf").read_text()
        self.assertIn(str(self.state / "private state"), dropin)

    def test_orphan_cleanup_only_signals_inir_thumbnail_workers(self):
        source = (ROOT / "scripts/inir").read_text()
        body = source[source.index("cleanup_orphans() {"):source.index("kill_shell() {")]
        self.assertNotIn('rm -rf', body)
        fake_proc = self.base / "proc"
        for pid, cgroup in [(4101, "ii.service"), (4102, "inir.service")]:
            folder = fake_proc / str(pid)
            folder.mkdir(parents=True)
            (folder / "cgroup").write_text("0::/user.slice/" + cgroup)
        body = body.replace("/proc/", str(fake_proc) + "/")
        output = self.bash(body + '''
systemctl() { printf 'MainPID=0\\n'; }
pgrep() { case "$*" in *scripts/thumbnails*) printf '4101\\n4102\\n';; esac; }
kill() { printf '%s\\n' "$*"; }
sleep() { :; }
cleanup_orphans
''')
        self.assertIn("4102", output)
        self.assertNotIn("4101", output)

    def test_official_install_entry_routes_once_with_flags(self):
        fixture = self.base / "official-entry"
        (fixture / ".git").mkdir(parents=True)
        (fixture / "shell.qml").touch()
        entry = fixture / "setup"
        entry.write_text((ROOT / "setup").read_text())
        personal = fixture / "scripts/personal"
        personal.mkdir(parents=True)
        (personal / "setup-entry.sh").write_text((ROOT / "scripts/personal/setup-entry.sh").read_text())
        wrapper = personal / "install.sh"
        wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$MOCK_SETUP_LOG"\n')
        wrapper.chmod(0o755)
        log = self.base / "entry.log"
        self.env["MOCK_SETUP_LOG"] = str(log)
        for options, expected in [(["install"], []), (["install", "-y"], ["-y"]),
                                  (["-y", "install", "-q"], ["-y", "-q"]),
                                  (["install", "--check"], ["--check"]),
                                  (["reinstall", "-y"], ["-y"]),
                                  (["reinstall", "--check"], ["--check"])]:
            subprocess.run(["bash", str(entry), *options], env=self.env, check=True, capture_output=True)
            self.assertEqual(log.read_text().strip().splitlines(), expected)
        log.unlink()
        self.env["INIR_PERSONAL_INSTALL_STAGE"] = "files"
        self.bash(f'source "{personal}/setup-entry.sh" install --skip-deps --skip-setups')
        self.assertFalse(log.exists(), "internal files stage must not recurse into wrapper")

    def kitty_generator_fixture(self):
        self.env["HOME"] = str(self.base)
        self.env.pop("INIR_INSTALL_SHARED_APP_CONFIGS", None)
        binary = self.base / "mock-bin"
        binary.mkdir()
        mock = binary / "pkill"
        mock.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_RELOAD_LOG"\n')
        mock.chmod(0o755)
        self.env.update(PATH=str(binary) + ":" + self.env["PATH"], MOCK_RELOAD_LOG=str(self.base / "reload.log"))
        palette = self.base / "palette.json"
        palette.write_text(json.dumps({"term0": "#112233", "term7": "#ccddee", "term15": "#eeeeff",
                                       "primary": "#aabbcc", "on_primary": "#001122", "error": "#ee4455"}))
        scss = self.base / "colors.scss"
        scss.write_text("$term0: #112233;\n$term7: #ccddee;\n$term15: #eeeeff;\n")
        theme = self.state / "quickshell/user/generated/terminal/kitty-theme.conf"
        theme.parent.mkdir(parents=True)
        theme.write_text("background #old-color\n")
        return theme, ["python3", str(ROOT / "scripts/colors/generate_terminal_configs.py"),
                       "--scss", str(scss), "--colors", str(palette),
                       "--terminal-json", str(palette), "--terminals", "kitty"]

    def test_kitty_generation_uses_ii_color_path_without_editing_base_config(self):
        theme, command = self.kitty_generator_fixture()
        kitty = self.config / "kitty"
        kitty.mkdir()
        config = kitty / "kitty.conf"
        config.write_text(f"globinclude {theme}\nfont_family FiraCode Nerd Font\nshell zsh\nremember_window_size no\n")
        original = config.read_bytes()
        link = kitty / "current-theme.conf"
        link.symlink_to(theme)
        original_link = link.readlink()
        for _ in range(2):
            subprocess.run(command, env=self.env, check=True, capture_output=True)
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(link.readlink(), original_link)
            self.assertEqual(link.resolve().read_bytes(), theme.read_bytes())
            self.assertFalse((kitty / "theme.conf").exists())
            self.assertIn("background              #112233", theme.read_text())
            self.assertIn("color255 #aabbcc", theme.read_text())
            self.assertIn("color232 #001122", theme.read_text())
            self.assertIn("color244 #ee4455", theme.read_text())
        self.assertEqual((self.base / "reload.log").read_text().splitlines(),
                         ["--signal SIGUSR1 -x kitty"] * 2)
        # Kitty's own parser must accept the generated file through the user's
        # existing include while retaining non-color settings.
        parsed = subprocess.run(["kitty", "+runpy", """
import os
from pathlib import Path
from kitty.config import load_config
bad = []
opts = load_config(str(Path(os.environ['XDG_CONFIG_HOME']) / 'kitty/kitty.conf'), accumulate_bad_lines=bad)
assert not bad, bad
assert opts.shell == 'zsh'
assert not opts.remember_window_size
assert int(opts.background) == 0x112233
assert int(opts.color255) == 0xaabbcc
print('Kitty config parser passed')
"""], env=self.env, capture_output=True, text=True, check=True)
        self.assertIn("Kitty config parser passed", parsed.stdout)

    def test_kitty_generation_does_not_create_or_replace_unrelated_config(self):
        theme, command = self.kitty_generator_fixture()
        subprocess.run(command, env=self.env, check=True, capture_output=True)
        kitty = self.config / "kitty"
        self.assertFalse(kitty.exists())
        kitty.mkdir()
        config = kitty / "kitty.conf"
        config.write_text("font_family Personal Font\ninclude my-theme.conf\n")
        link = kitty / "current-theme.conf"
        link.symlink_to("my-theme.conf")
        custom = kitty / "my-theme.conf"
        custom.write_text("background #ffffff\n")
        subprocess.run(command, env=self.env, check=True, capture_output=True)
        self.assertEqual(config.read_text(), "font_family Personal Font\ninclude my-theme.conf\n")
        self.assertEqual(link.readlink(), Path("my-theme.conf"))
        self.assertEqual(custom.read_text(), "background #ffffff\n")
        self.assertIn("#112233", theme.read_text())

    def test_kitty_config_integration_requires_explicit_opt_in(self):
        theme, command = self.kitty_generator_fixture()
        self.env["INIR_INSTALL_SHARED_APP_CONFIGS"] = "true"
        subprocess.run(command, env=self.env, check=True, capture_output=True)
        kitty = self.config / "kitty"
        self.assertEqual((kitty / "current-theme.conf").resolve(), theme)
        self.assertEqual((kitty / "kitty.conf").read_text(), "include current-theme.conf\n")

    def test_menu_install_cannot_bypass_personal_wrapper(self):
        source = (ROOT / "setup").read_text()
        body = source[source.index("run_install() {"):source.index("    detect_distro", source.index("run_install() {"))]
        fixture = self.base / "menu"
        personal = fixture / "scripts/personal"
        personal.mkdir(parents=True)
        wrapper = personal / "install.sh"
        wrapper.write_text('#!/bin/sh\nprintf "wrapper: %s\\n" "$*"\n')
        wrapper.chmod(0o755)
        self.env["REPO_ROOT"] = str(fixture)
        self.assertEqual(self.bash(body + "\n}\nask=false; quiet=true; run_install").strip(), "wrapper: -y --quiet")

    def test_legacy_cleanup_keeps_ii_service(self):
        source = (ROOT / "sdata/subcmd-install/2.setups.sh").read_text()
        body = source[source.index("function disable_super_daemon_if_present(){"):].split("\n}", 1)[0] + "\n}"
        self.env["HOME"] = str(self.base)
        unit = self.config / "systemd/user/ii-super-overview.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("II service")
        daemon = self.base / ".local/bin/ii_super_overview_daemon.py"
        daemon.parent.mkdir(parents=True)
        daemon.write_text("II daemon")
        self.bash(body + "\ndisable_super_daemon_if_present")
        self.assertEqual(unit.read_text(), "II service")
        self.assertEqual(daemon.read_text(), "II daemon")

    def test_update_preserves_existing_vesktop_theme(self):
        source = (ROOT / "setup").read_text()
        block = source.split("    # Update Vesktop themes", 1)[1].split("    # Migrations", 1)[0]
        block = block[block.index("    if "):]
        theme = self.config / "vesktop/themes/ii-system24.theme.css"
        theme.parent.mkdir(parents=True)
        theme.write_text("personal theme")
        self.env.pop("INIR_INSTALL_SHARED_APP_CONFIGS", None)
        self.bash(block)
        self.assertEqual(theme.read_text(), "personal theme")

    def test_gamemode_command_handles_spaces(self):
        # QML string syntax is JSON-compatible for this command.
        line = next(line for line in (ROOT / "services/GameMode.qml").read_text().splitlines()
                    if '"mkdir -p ' in line)
        command = json.loads(line.strip().rstrip(","))
        target = self.base / "state with spaces/user/gamemode_active"
        subprocess.run(["bash", "-c", command, "inir-gamemode", str(target.parent), "1", str(target)], check=True)
        self.assertEqual(target.read_text(), "1\n")


if __name__ == "__main__":
    unittest.main()
