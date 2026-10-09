#!/usr/bin/env python3
"""Isolated supervisor write/cleanup regressions; never touch the live session."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inir-supervisor-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "config"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.startup = self.config / "niri/config.d/50-startup.kdl"
        self.startup.parent.mkdir(parents=True)
        self.startup.write_text("// fixture startup\n")
        self.launcher = self.bin / "inir"
        self.launcher.write_text("#!/bin/sh\nexit 0\n")
        self.launcher.chmod(0o755)
        for name in ("cat", "chmod", "dirname", "grep", "install", "mkdir", "rm", "sed", "touch"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.bin / name).symlink_to(str(executable))
        (self.bin / "python3").symlink_to(sys.executable)
        self.examples = self.base / "examples"
        self.examples.mkdir()
        for name in ("dbus.run", "dbus.check"):
            (self.examples / name).write_text("#!/bin/sh\nexit 0\n")
        self.env = dict(os.environ, HOME=str(self.base / "home"), XDG_CONFIG_HOME=str(self.config),
                        XDG_STATE_HOME=str(self.base / "state"), XDG_DATA_HOME=str(self.base / "data"),
                        XDG_CACHE_HOME=str(self.base / "cache"), XDG_RUNTIME_DIR=str(self.base / "runtime"),
                        XDG_BIN_HOME=str(self.bin), REPO_ROOT=str(ROOT), TMPDIR=str(self.base),
                        PATH=str(self.bin), INIR_TURNSTILE_EXAMPLES=str(self.examples),
                        OS_GROUP_ID="void", INSTALL_TOOLKIT="true")
        for name in ("INIR_RUNTIME_DIR", "INIR_CONFIG_DIR", "INIR_STATE_DIR", "INIR_VENV", "DOTS_CORE_CONFDIR"):
            self.env.pop(name, None)
        self.calls = self.base / "calls"

    def shell(self, code="reconcile_inir_supervisor", supervisor="runsvdir", inject=""):
        script = '''source "$REPO_ROOT/sdata/lib/functions.sh"
inir_supervisor() { printf '%s\\n' "$FIXTURE_SUPERVISOR"; }
has_usable_systemd_user_manager() { [[ "$FIXTURE_SUPERVISOR" == systemd ]]; }
pipewire() { :; }
wireplumber() { :; }
pipewire-pulse() { :; }
ydotoold() { printf 'fixture-version\\n'; }
xembedsniproxy() { :; }
sv() { printf 'sv %s\\n' "$*" >> "$TMPDIR/calls"; }
systemctl() { printf 'systemctl %s\\n' "$*" >> "$TMPDIR/calls"; }
'''
        env = dict(self.env, FIXTURE_SUPERVISOR=supervisor)
        # Deliberately no errexit: callers use conditionals/command substitution,
        # which otherwise hide missing explicit failure propagation.
        return subprocess.run(["/bin/bash", "-c", script + inject + "\n" + code],
                              env=env, capture_output=True, text=True, timeout=15)

    def alias(self, relative):
        shared = self.config / "quickshell/ii"
        shared.mkdir(parents=True, exist_ok=True)
        destination = self.config / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith(("/run", "/check", "/conf", ".kdl", ".service")):
            target = shared / "sentinel"
            target.write_text("# Managed by iNiR.\nII sentinel\n")
        else:
            target = shared / "directory"
            target.mkdir(exist_ok=True)
            (target / "run").write_text("# Managed by iNiR.\nII sentinel\n")
            (target / "keep").write_text("II directory sentinel\n")
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.symlink_to(target)
        return shared

    def snapshot(self, directory):
        return {str(path.relative_to(directory)): path.read_bytes()
                for path in directory.rglob("*") if path.is_file()}

    def assert_alias_rejected(self, relative, supervisor="runsvdir", code="reconcile_inir_supervisor"):
        shared = self.alias(relative)
        before = self.snapshot(shared)
        startup = self.startup.read_bytes() if self.startup.exists() else None
        result = self.shell(code, supervisor)
        self.assertNotEqual(result.returncode, 0, f"accepted {relative}: {result.stdout} {result.stderr}")
        self.assertEqual(self.snapshot(shared), before, f"II modified through {relative}")
        if startup is not None:
            self.assertEqual(self.startup.read_bytes(), startup)
        self.assertFalse((self.config / "service/inir/run").exists()
                         and not relative.startswith("service/inir"), "wrote before preflight")
        self.assertFalse(self.calls.exists(), "called service tools before preflight")

    def test_rejects_service_root_alias_before_any_writes(self):
        self.assert_alias_rejected("service")

    def test_rejects_inir_directory_alias_before_any_writes(self):
        self.assert_alias_rejected("service/inir")

    def test_rejects_inir_run_alias_before_any_writes(self):
        self.assert_alias_rejected("service/inir/run")

    def test_rejects_xembed_directory_alias_before_any_writes(self):
        self.assert_alias_rejected("service/inir-xembedsniproxy")

    def test_rejects_xembed_run_alias_before_any_writes(self):
        self.assert_alias_rejected("service/inir-xembedsniproxy/run")

    def test_systemd_rejects_xembed_alias_before_cleanup(self):
        self.assert_alias_rejected("service/inir-xembedsniproxy", "systemd")

    def test_rejects_startup_directory_alias_before_any_writes(self):
        self.assert_alias_rejected("niri/config.d")

    def test_rejects_startup_file_alias_before_any_writes(self):
        self.assert_alias_rejected("niri/config.d/50-startup.kdl")

    def test_rejects_fallback_startup_file_alias_before_any_writes(self):
        self.startup.unlink()
        self.assert_alias_rejected("niri/config.kdl")

    def test_rejects_audio_directory_alias_before_any_writes(self):
        self.assert_alias_rejected("service/pipewire")

    def test_rejects_audio_run_alias_before_any_writes(self):
        self.assert_alias_rejected("service/wireplumber/run")

    def test_audio_helper_rejects_run_alias_when_called_directly(self):
        self.assert_alias_rejected("service/pipewire/run", code='reconcile_audio_user_services runsvdir')

    def test_rejects_ydotool_run_alias_before_any_writes(self):
        self.assert_alias_rejected("service/ydotool/run")

    def test_ydotool_helper_rejects_directory_alias_when_called_directly(self):
        self.assert_alias_rejected("service/ydotool", code='reconcile_ydotool_user_service runsvdir true')

    def test_rejects_ydotool_unit_alias_before_any_writes(self):
        self.assert_alias_rejected("systemd/user/ydotool.service", "systemd")

    def test_rejects_turnstile_dbus_run_alias_before_any_writes(self):
        self.assert_alias_rejected("service/dbus/run", "turnstile")

    def test_rejects_turnstile_ready_conf_alias_before_any_writes(self):
        self.assert_alias_rejected("service/turnstile-ready/conf", "turnstile")

    def test_turnstile_helper_rejects_check_alias_when_called_directly(self):
        self.assert_alias_rejected("service/dbus/check", "turnstile", 'configure_turnstile_user_services')

    def test_systemd_does_not_create_inir_runit_launch_file(self):
        result = self.shell(supervisor="systemd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.config / "service/inir").exists())
        self.assertFalse((self.config / "service/inir-xembedsniproxy").exists())
        self.assertIn("BEGIN inir-systemd-environment", self.startup.read_text())

    def assert_failure_propagated(self, inject, supervisor="runsvdir", code="reconcile_inir_supervisor"):
        before = self.startup.read_bytes()
        result = self.shell(code, supervisor, inject)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(supervisor + "\n", result.stdout)
        self.assertEqual(self.startup.read_bytes(), before)

    def test_propagates_inir_mkdir_failure(self):
        self.assert_failure_propagated('mkdir() { [[ "$*" != *service/inir* ]] && command mkdir "$@"; }')

    def test_propagates_inir_printf_failure(self):
        self.assert_failure_propagated('printf() { [[ "$1" != *"run --session"* ]] && builtin printf "$@"; }')

    def test_propagates_inir_chmod_failure(self):
        self.assert_failure_propagated('chmod() { [[ "$*" != *service/inir/run* ]] && command chmod "$@"; }')

    def test_propagates_inir_redirection_failure(self):
        (self.config / "service/inir/run").mkdir(parents=True)
        self.assert_failure_propagated("")

    def test_propagates_xembed_mkdir_failure(self):
        self.assert_failure_propagated('mkdir() { [[ "$*" != *inir-xembedsniproxy* ]] && command mkdir "$@"; }')

    def test_propagates_xembed_write_failure(self):
        self.assert_failure_propagated('cat() { return 71; }')

    def test_propagates_xembed_chmod_failure(self):
        self.assert_failure_propagated('chmod() { [[ "$*" != *inir-xembedsniproxy* ]] && command chmod "$@"; }')

    def test_propagates_startup_python_failure(self):
        self.assert_failure_propagated('python3() { return 71; }')

    def test_propagates_startup_write_failure(self):
        self.assert_failure_propagated('''python3() {
  { builtin printf 'from pathlib import Path\ndef fail_write(*args, **kwargs):\n    raise OSError("fixture write failure")\nPath.write_text = fail_write\n'; command cat; } | command python3 "$@"
}''')

    def test_propagates_turnstile_mkdir_failure(self):
        self.assert_failure_propagated('mkdir() { [[ "$*" != *service/dbus* ]] && command mkdir "$@"; }', "turnstile")

    def test_propagates_turnstile_install_failure(self):
        self.assert_failure_propagated('install() { return 71; }', "turnstile")

    def test_propagates_turnstile_touch_failure(self):
        self.assert_failure_propagated('touch() { return 71; }', "turnstile")

    def test_propagates_turnstile_conf_append_failure(self):
        self.assert_failure_propagated('printf() { [[ "$1" != *core_services* ]] && builtin printf "$@"; }', "turnstile")

    def test_propagates_turnstile_conf_rewrite_failure(self):
        conf = self.config / "service/turnstile-ready/conf"
        conf.parent.mkdir(parents=True)
        conf.write_text('core_services="other"\n')
        self.assert_failure_propagated('sed() { [[ "$1" != -i ]] && command sed "$@"; }', "turnstile")

    def test_propagates_ydotool_unit_mkdir_failure(self):
        self.assert_failure_propagated('mkdir() { [[ "$*" != *systemd/user* ]] && command mkdir "$@"; }', "systemd")

    def test_propagates_ydotool_cleanup_failure(self):
        run = self.config / "service/ydotool/run"
        run.parent.mkdir(parents=True)
        run.write_text("# Managed by iNiR.\n")
        self.assert_failure_propagated('rm() { return 71; }', "systemd")

    def test_propagates_launcher_quote_rewrite_failure(self):
        self.assert_failure_propagated('sed() { return 71; }')

    def test_propagates_launcher_quote_printf_failure(self):
        self.assert_failure_propagated('printf() { [[ "$1" != %s ]] && builtin printf "$@"; }')

    def test_propagates_audio_quote_rewrite_failure(self):
        self.assert_failure_propagated('sed() { return 71; }', code='reconcile_audio_user_services runsvdir')

    def test_propagates_audio_quote_printf_failure(self):
        self.assert_failure_propagated('printf() { [[ "$1" != %s ]] && builtin printf "$@"; }',
                                       code='reconcile_audio_user_services runsvdir')

    def test_propagates_supervisor_detection_failure(self):
        self.assert_failure_propagated('inir_supervisor() { return 71; }')

    def test_runit_supervisors_write_executable_launchers_idempotently(self):
        for supervisor in ("runsvdir", "turnstile"):
            with self.subTest(supervisor=supervisor):
                first = self.shell(supervisor=supervisor)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(first.stdout, supervisor + "\n")
                run = self.config / "service/inir/run"
                self.assertTrue(os.access(run, os.X_OK))
                self.assertIn("run --session", run.read_text())
                self.assertEqual("chpst" in run.read_text(), supervisor == "turnstile")
                before = self.snapshot(self.config)
                second = self.shell(supervisor=supervisor)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self.snapshot(self.config), before)

    def test_systemd_accepts_expected_ydotool_wants_link(self):
        unit = self.config / "systemd/user/ydotool.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("# Managed by iNiR.\n")
        wants = unit.parent / "default.target.wants/ydotool.service"
        wants.parent.mkdir()
        wants.symlink_to(unit)
        result = self.shell(supervisor="systemd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(wants.is_symlink())

    def test_audio_preserves_unowned_run_file(self):
        run = self.config / "service/pipewire/run"
        run.parent.mkdir(parents=True)
        run.write_text("#!/bin/sh\n# User-owned fixture\n")
        before = run.read_bytes()
        result = self.shell()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
