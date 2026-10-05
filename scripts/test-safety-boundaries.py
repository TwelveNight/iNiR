#!/usr/bin/env python3
"""Synthetic destructive-boundary checks. Never use live desktop paths."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-safety-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.state = self.base / "state"
        self.config.mkdir()
        self.state.mkdir()
        self.env = dict(os.environ, HOME=str(self.base), XDG_CONFIG_HOME=str(self.config),
                        XDG_STATE_HOME=str(self.state), XDG_DATA_HOME=str(self.base / "data"),
                        XDG_CACHE_HOME=str(self.base / "cache"), XDG_BIN_HOME=str(self.base / "bin"),
                        REPO_ROOT=str(ROOT), TMPDIR=str(self.base))
        for key in ["DOTS_CORE_CONFDIR", "INIR_CONFIG_DIR", "INIR_STATE_DIR", "INIR_VENV", "INIR_RUNTIME_DIR"]:
            self.env.pop(key, None)
        self.env["INIR_INSTALL_SHARED_APP_CONFIGS"] = "false"

    def run_command(self, args, **kwargs):
        return subprocess.run(args, env=self.env, capture_output=True, text=True, **kwargs)

    def shell(self, code, *args):
        return self.run_command(["bash", "-c", code, "fixture", str(ROOT), *map(str, args)])

    def widget(self, action, name="clock", root=None):
        return self.run_command(["python3", str(ROOT / "scripts/widgets/manage.py"), action,
                                 str(root or self.config / "inir/widgets"), name])

    def test_widget_create_scan_remove_in_shell_sensitive_path(self):
        root = self.base / 'widgets $(touch INJECTION) "quote"'
        result = self.widget("create", "my-clock", root)
        self.assertEqual(result.returncode, 0, result.stderr)
        widget = root / "my-clock"
        self.assertTrue((widget / "MyClock.qml").exists())
        original = (widget / "MyClock.qml").read_bytes()
        self.assertNotEqual(self.widget("create", "my-clock", root).returncode, 0)
        self.assertEqual((widget / "MyClock.qml").read_bytes(), original)
        scanned = self.run_command(["bash", str(ROOT / "scripts/scan-widgets.sh"), str(root)], check=True)
        self.assertEqual(json.loads(scanned.stdout)[0]["dir"], str(widget))
        self.assertEqual(self.widget("remove", "my-clock", root).returncode, 0)
        self.assertFalse(widget.exists())
        self.assertFalse((ROOT / "INJECTION").exists())

    def test_widgets_reject_traversal_commands_and_symlinks(self):
        root = self.config / "inir/widgets"
        root.mkdir(parents=True)
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = outside / "keep"
        sentinel.write_text("keep")
        for name in ["..", "../outside", str(outside), 'x$(touch BAD)', 'x"; false; #', ""]:
            for action in ["create", "remove"]:
                self.assertNotEqual(self.widget(action, name).returncode, 0, (action, name))
        (root / "linked").symlink_to(outside)
        self.assertNotEqual(self.widget("remove", "linked").returncode, 0)
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(self.widget("example", "example-widget").returncode, 0)
        (root / "example-widget/widget.json").write_text('{"main":"../../outside.qml"}')
        scanned = self.run_command(["bash", str(ROOT / "scripts/scan-widgets.sh"), str(root)], check=True)
        self.assertEqual(json.loads(scanned.stdout), [])

    def test_maintenance_and_launcher_reject_ii_aliases_before_writes(self):
        ii = self.config / "illogical-impulse"
        ii.mkdir()
        sentinel = ii / "config.json"
        sentinel.write_text("II settings")
        alias = self.config / "alias"
        alias.symlink_to(ii)
        for key in ["DOTS_CORE_CONFDIR", "INIR_CONFIG_DIR", "INIR_STATE_DIR", "INIR_VENV"]:
            with self.subTest(key=key):
                self.env[key] = str(alias)
                for command in ["update", "uninstall", "rollback", "status"]:
                    result = self.run_command(["bash", str(ROOT / "setup"), command, "-y"])
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("Unsafe iNiR paths", result.stderr)
                result = self.run_command(["bash", str(ROOT / "scripts/inir"), "status"])
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                del self.env[key]
        self.assertEqual(sentinel.read_text(), "II settings")

    def test_private_paths_reject_broad_or_overlapping_overrides(self):
        validator = ["python3", str(ROOT / "scripts/lib/private_paths.py")]
        for key, value in [("INIR_CONFIG_DIR", self.base), ("INIR_STATE_DIR", self.config / "kitty"),
                           ("INIR_VENV", self.state / "inir"), ("INIR_CONFIG_DIR", "relative"),
                           ("INIR_CONFIG_DIR", str(self.base / "new\nline"))]:
            self.env[key] = str(value)
            self.assertEqual(self.run_command(validator).returncode, 2)
            del self.env[key]
        self.assertEqual(self.run_command(validator).returncode, 0)
        self.env["INIR_CONFIG_DIR"] = str(self.base / "private settings")
        self.assertEqual(self.run_command(validator).returncode, 0)

    def test_runtime_and_backup_links_cannot_redirect_maintenance_into_ii(self):
        ii = self.config / "quickshell/ii"
        ii.mkdir(parents=True)
        runtime = self.config / "quickshell/inir"
        runtime.mkdir()
        (runtime / "services").symlink_to(ii)
        command = ["python3", str(ROOT / "scripts/lib/private_paths.py"), "--runtime-links"]
        self.assertEqual(self.run_command(command).returncode, 2)
        (runtime / "services").unlink()
        own_state = self.state / "inir"
        own_state.mkdir()
        shared = self.state / "quickshell/backups"
        shared.mkdir(parents=True)
        (own_state / "backups").symlink_to(shared)
        self.assertEqual(self.run_command(command).returncode, 2)

    def test_install_file_and_directory_refuse_destination_symlinks(self):
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = outside / "shared"
        sentinel.write_text("keep")
        source = self.base / "source"
        source.write_text("overwrite")
        link = self.base / "link"
        link.symlink_to(sentinel)
        code = '''source "$1/sdata/lib/functions.sh"
x() { "$@"; }
INSTALLED_LISTFILE="$TMPDIR/installed"
cp_file "$2" "$3"
'''
        self.assertNotEqual(self.shell(code, source, link).returncode, 0)
        link.unlink()
        link.symlink_to(outside)
        code = '''source "$1/sdata/lib/functions.sh"
x() { "$@"; }
INSTALLED_LISTFILE="$TMPDIR/installed"
rsync_dir__sync "$1/services" "$2"
'''
        self.assertNotEqual(self.shell(code, link).returncode, 0)
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(len(list(outside.iterdir())), 1)

    def test_failed_update_backup_keeps_previous_backups_and_marker(self):
        backups = self.state / "inir/backups"
        backups.mkdir(parents=True)
        for index in range(7):
            (backups / f"pre-update-old-{index}").mkdir()
        marker = backups / ".last-backup"
        marker.write_text("last successful backup")
        result = self.shell('''source "$1/sdata/lib/robust-update.sh"
rsync() { return 23; }
create_update_backup "$TMPDIR/missing-source"
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), "last successful backup")
        self.assertEqual(len(list(backups.glob("pre-update-old-*"))), 7)

        source = self.base / "runtime-source"
        source.mkdir(mode=0o755)
        (source / "shell.qml").write_text("synthetic source")
        sentinel = self.base / "marker-sentinel"
        sentinel.write_text("preserve me")
        marker.unlink()
        marker.symlink_to(sentinel)
        result = self.shell('''source "$1/sdata/lib/robust-update.sh"
create_update_backup "$TMPDIR/runtime-source"
create_update_backup "$TMPDIR/runtime-source"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        first, second = map(Path, result.stdout.splitlines())
        self.assertNotEqual(first, second)
        self.assertEqual(second.stat().st_mode & 0o777, 0o700)
        self.assertEqual((second / "shell.qml").read_text(), "synthetic source")
        self.assertFalse(marker.is_symlink())
        self.assertEqual(sentinel.read_text(), "preserve me")

    def test_aur_helpers_only_clean_their_own_unique_build_directory(self):
        for name in ["buildyay", "buildparu"]:
            (self.base / name).mkdir()
            (self.base / name / "keep").write_text("other job")
        result = self.shell('''source "$1/sdata/lib/package-installers.sh"
tui_info() { :; }
x() { "$@"; }
pkg_sudo() { printf '%s\\n' "$*" >> "$TMPDIR/commands"; }
git() { mkdir -p "$3"; }
makepkg() { return 7; }
install-yay
first=$?
install-paru
second=$?
[[ "$first" == 7 && "$second" == 7 ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(list(self.base.glob("inir-yay.*")))
        self.assertFalse(list(self.base.glob("inir-paru.*")))
        self.assertEqual((self.base / "buildyay/keep").read_text(), "other job")
        self.assertEqual((self.base / "buildparu/keep").read_text(), "other job")
        self.assertNotIn("-Sy", (self.base / "commands").read_text())

    def test_chrome_never_prepares_system_policy_permissions(self):
        source = (ROOT / "scripts/colors/apply-chrome-theme.sh").read_text()
        function = source.split("ensure_policy_dir_writable() {", 1)[1].split("# ── Resolve theme color", 1)[0]
        self.env["INIR_INSTALL_SHARED_APP_CONFIGS"] = "true"
        result = self.shell('''log() { :; }
elevate() { touch "$TMPDIR/elevated"; }
ensure_policy_dir_writable() {''' + function + '\nensure_policy_dir_writable "$TMPDIR/new-policies" fixture\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "new-policies").exists())
        self.assertFalse((self.base / "elevated").exists())

    def test_uninstall_backup_is_private_and_failure_stops_deletion(self):
        private = self.config / "inir"
        private.mkdir()
        (private / "config.json").write_text('{"fixture":"not a credential"}')
        result = self.shell('''source "$1/sdata/lib/uninstall.sh"
tui_info() { :; }
tui_success() { :; }
uninstall_create_backup
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual((backup / "inir/config.json").read_bytes(), (private / "config.json").read_bytes())
        result = self.shell('''source "$1/sdata/lib/uninstall.sh"
tui_title() { :; }; tui_info() { :; }; tui_warn() { :; }; tui_confirm() { return 0; }
uninstall_stop_services() { touch "$TMPDIR/stopped"; }
uninstall_remove_inir_only() { touch "$TMPDIR/removed"; }
cp() { return 28; }
run_uninstall_quick
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "stopped").exists())
        self.assertFalse((self.base / "removed").exists())
        self.assertTrue((private / "config.json").exists())

    def test_uninstall_keeps_shared_sddm_helper(self):
        helper = self.base / ".local/bin/sync-pixel-sddm.py"
        helper.parent.mkdir(parents=True)
        helper.write_text("shared helper")
        private = self.config / "inir"
        private.mkdir()
        (private / "config.json").write_text("synthetic settings")
        result = self.shell('''source "$1/sdata/lib/uninstall.sh"
tui_info() { :; }; tui_success() { :; }
uninstall_remove_inir_only
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(helper.read_text(), "shared helper")
        self.assertFalse(private.exists())

    def test_package_and_sddm_migrations_cannot_bypass_personal_install(self):
        result = self.shell('''source "$1/sdata/lib/migrations.sh"
tui_check_skip() { :; }
pkg_sudo() { touch "$TMPDIR/unexpected-package-write"; return 99; }
for id in 012-plasma-integration-qt-theming 029-plasma-browser-integration 039-sddm-preserve-greeter-backend; do
    is_migration_needed "$id" && exit 1
    apply_migration "$id" true || exit 1
done
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.base / "unexpected-package-write").exists())

    def test_steam_migration_only_converts_private_setting(self):
        private = self.config / "inir/config.json"
        private.parent.mkdir()
        private.write_text('{"appearance":{"wallpaperTheming":{"enableAdwSteam":true}}}')
        shared = self.config / "millennium/config.json"
        shared.parent.mkdir()
        shared.write_text('{"themes":{"activeTheme":"personal"}}')
        result = self.shell('''source "$1/sdata/migrations/024-steam-millennium.sh"
migration_apply
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(private.read_text())["appearance"]["wallpaperTheming"]["enableSteam"])
        self.assertEqual(shared.read_text(), '{"themes":{"activeTheme":"personal"}}')

    def test_missing_deno_does_not_download_or_replace_shared_binary(self):
        binary = self.base / "bin/deno"
        binary.parent.mkdir()
        binary.write_text("personal runtime sentinel")
        result = self.shell('''source "$1/sdata/lib/package-installers.sh"
ytmusic-deno-compatible() { return 1; }
log_warning() { :; }
curl() { touch "$TMPDIR/unexpected-download"; return 99; }
ensure-ytmusic-js-runtime
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.base / "unexpected-download").exists())
        self.assertEqual(binary.read_text(), "personal runtime sentinel")

    def test_install_resource_stage_preserves_wallpapers_and_shared_theme(self):
        # Execute the real resource/theme stage with synthetic paths and hooks.
        text = (ROOT / "sdata/subcmd-install/3.files.sh").read_text()
        stage = text[text.index('tui_info "Copying wallpapers..."'):text.index('# Reset first run marker')]
        stage_path = self.base / "resource-stage.sh"
        stage_path.write_text(stage)
        runtime = self.config / "quickshell/inir"
        (runtime / "assets/wallpapers").mkdir(parents=True)
        (runtime / "assets/wallpapers/existing.jpg").write_text("bundled replacement")
        (runtime / "scripts/colors").mkdir(parents=True)
        (runtime / "scripts/colors/apply-gtk-theme.sh").write_text('touch "$HOME/unexpected-theme"\n')
        generated = self.state / "quickshell/user/generated"
        generated.mkdir(parents=True)
        (generated / "material_colors.scss").write_text("shared palette sentinel")
        wallpaper = self.base / "Pictures/Wallpapers/existing.jpg"
        wallpaper.parent.mkdir(parents=True)
        wallpaper.touch()  # Old installer overwrote existing empty files.
        for interactive in ["false", "true"]:
            result = self.shell('''tui_info() { :; }; log_info() { :; }; log_success() { :; }
tui_confirm() { return 0; }
extras_install_yamis_icons() { touch "$HOME/unexpected-icons"; }
extras_install_inir_walls() { touch "$HOME/unexpected-walls"; }
xdg-user-dir() { printf '%s/Pictures\\n' "$HOME"; }
INSTALL_FIRSTRUN=true
INIR_WALLPAPER_BACKEND=skwd-wall
ask="$3"
source "$2"
''', stage_path, interactive)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(wallpaper.read_bytes(), b"")
        self.assertEqual((generated / "material_colors.scss").read_text(), "shared palette sentinel")
        for action in ["theme", "icons", "walls"]:
            self.assertFalse((self.base / f"unexpected-{action}").exists())
        self.assertFalse((self.base / "data/color-schemes").exists())


if __name__ == "__main__":
    unittest.main()
