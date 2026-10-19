#!/usr/bin/env python3
"""Exercise upstream integration and failed-deploy boundaries in temporary repos."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("desktop_update", ROOT / "scripts/personal/desktop-update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="desktop-update-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.repo = self.home / "source with spaces"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "night/personal-overlay")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", "https://github.com/snowarch/iNiR.git")
        (self.repo / "base").write_text("original\n")
        self.git("add", "base")
        self.git("commit", "-qm", "base")
        self.git("branch", "upstream")

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.repo), *arguments], text=True, stderr=subprocess.PIPE).strip()

    def branches(self, conflict=False):
        self.git("switch", "-q", "upstream")
        (self.repo / ("base" if conflict else "upstream-file")).write_text("upstream\n")
        self.git("add", ".")
        self.git("commit", "-qm", "upstream change")
        self.git("update-ref", "refs/remotes/origin/prerelease", "HEAD")
        self.git("switch", "-q", "night/personal-overlay")
        (self.repo / ("base" if conflict else "personal-file")).write_text("personal\n")
        self.git("add", ".")
        self.git("commit", "-qm", "personal change")

    def no_network(self, command, **kwargs):
        if "fetch" in command:
            self.assertEqual(command[-2:], ["origin", "+refs/heads/prerelease:refs/remotes/origin/prerelease"])
            self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
            self.assertEqual(kwargs["timeout"], 60)
            return ""
        self.assertNotIn("reset", command)
        self.assertNotIn("rebase", command)
        self.assertNotIn("push", command)
        return self.original_run(command, **kwargs)

    def test_sync_merges_upstream_and_retains_personal_commit(self):
        self.branches()
        personal = self.git("rev-parse", "HEAD")
        self.original_run = update.run
        with patch.object(update, "run", side_effect=self.no_network):
            update.sync("inir", self.repo)
        self.git("merge-base", "--is-ancestor", personal, "HEAD")
        self.assertEqual((self.repo / "personal-file").read_text(), "personal\n")
        self.assertTrue((self.repo / "upstream-file").is_file())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertTrue(self.git("for-each-ref", "refs/desktop-updates/"))

    def test_conflict_keeps_working_tree_for_review(self):
        self.branches(conflict=True)
        self.original_run = update.run
        with patch.object(update, "run", side_effect=self.no_network), \
                patch.object(update.shutil, "which", return_value=None), \
                self.assertRaisesRegex(ValueError, "打开 AI"):
            update.sync("inir", self.repo)
        self.assertTrue((self.repo / ".git/MERGE_HEAD").is_file())
        self.assertIn("<<<<<<<", (self.repo / "base").read_text())

    def registry(self, names=("inir",)):
        registry = self.home / ".config/desktop-profiles/profiles.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({name: {"source": str(self.repo)} for name in names}))

    def test_online_check_reports_upstream_without_rejecting_local_work(self):
        self.branches()
        self.registry()
        (self.repo / "pending-work").write_text("preserve me")
        original = self.git("rev-parse", "HEAD")
        self.original_run = update.run
        output = io.StringIO()
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(update, "run", side_effect=self.no_network), \
                contextlib.redirect_stdout(output):
            self.assertEqual(update.main(["check", "inir", "--json"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual((report["behind"], report["ahead"], report["status"]), (1, 1, "behind"))
        self.assertEqual(report["upstream"], "origin/prerelease")
        self.assertEqual(self.git("rev-parse", "HEAD"), original)
        self.assertEqual((self.repo / "pending-work").read_text(), "preserve me")

    def test_existing_conflict_repeats_ai_instructions_without_fetch(self):
        self.branches(conflict=True)
        subprocess.run(["git", "-C", str(self.repo), "merge", "--no-edit", "upstream"], capture_output=True)
        with patch.object(update.shutil, "which", return_value=None), \
                self.assertRaisesRegex(ValueError, "打开 AI"):
            update.check_source("inir", self.repo)
        self.assertTrue((self.repo / ".git/MERGE_HEAD").is_file())

    def test_vitreus_wm_alias_syncs_shared_checkout_once_without_live_write(self):
        self.registry(("vitreus", "vitreus-wm"))
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(update, "check_source"), patch.object(update, "sync") as sync, \
                patch.object(update, "checks", return_value=[]), \
                patch.object(update, "profile_manager", return_value=Mock()), \
                patch.object(update, "snapshot") as backup:
            self.assertEqual(update.main(["sync", "vitreus-wm"]), 0)
        sync.assert_called_once_with("vitreus", self.repo)
        backup.assert_not_called()
        self.assertEqual(update.deploy_command("vitreus", self.repo),
                         ["python3", "-B", self.repo / "personal/install.py", "--apply"])

    def test_conflict_in_update_never_runs_verification_or_deployment(self):
        self.branches(conflict=True)
        self.registry()
        self.original_run = update.run
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(update, "run", side_effect=self.no_network), \
                patch.object(update.shutil, "which", return_value=None), \
                patch.object(update, "checks") as checks, patch.object(update, "snapshot") as backup:
            with self.assertRaisesRegex(ValueError, "live 未更新"):
                update.main(["update", "inir"])
        checks.assert_not_called()
        backup.assert_not_called()

    def test_dirty_source_and_wrong_branch_are_rejected(self):
        (self.repo / "uncommitted").write_text("user work\n")
        with self.assertRaises(ValueError):
            update.check_source("inir", self.repo)
        (self.repo / "uncommitted").unlink()
        self.git("switch", "-q", "upstream")
        with self.assertRaises(ValueError):
            update.check_source("inir", self.repo)

    def test_verification_failure_never_snapshots_or_deploys(self):
        registry = self.home / ".config/desktop-profiles/profiles.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"inir": {"source": str(self.repo)}}))
        with patch.object(Path, "home", return_value=self.home), patch.object(update, "checks", return_value=[["false"]]), patch.object(update, "snapshot") as backup:
            with self.assertRaises(subprocess.CalledProcessError):
                update.main(["deploy", "inir"])
        backup.assert_not_called()

    def test_plan_has_no_fetch_write_or_deploy(self):
        registry = self.home / ".config/desktop-profiles/profiles.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"inir": {"source": str(self.repo)}}))
        with patch.object(Path, "home", return_value=self.home), patch.object(update, "sync") as sync, patch.object(update, "snapshot") as backup:
            self.assertEqual(update.main(["update", "inir", "--plan"]), 0)
        sync.assert_not_called()
        backup.assert_not_called()
        self.assertFalse((self.home / ".local/state").exists())

    def test_chezmoi_updates_only_files_changed_by_installer(self):
        target = self.home / "config"
        target.write_text("new\n")
        with patch.object(update, "run", return_value="old\n") as run:
            update.chezmoi_after({target: (b"old\n", "old\n")})
        self.assertEqual(run.call_args_list[1].args[0], ["chezmoi", "re-add", "--", target])
        self.assertEqual(run.call_args_list[2].args[0], ["chezmoi", "apply", "--", target])

    def test_independent_chezmoi_edit_blocks_readd(self):
        target = self.home / "config"
        target.write_text("installed\n")
        with patch.object(update, "run") as run, self.assertRaises(ValueError):
            update.chezmoi_after({target: (b"old live\n", "unapplied user edit")})
        run.assert_not_called()

    def test_entry_installs_into_the_target_home(self):
        env = dict(os.environ, HOME=str(self.home))
        subprocess.run(["bash", str(ROOT / "scripts/personal/install-desktop-update.sh")], env=env, check=True)
        helper = self.home / ".local/bin/desktop-update"
        result = subprocess.run([str(helper), "--help"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sync", result.stdout)
        self.assertEqual((self.home / ".local/lib/desktop-profiles/desktop_update.py").read_bytes(), (ROOT / "scripts/personal/desktop-update.py").read_bytes())
        service = (self.home / ".config/systemd/user/desktop-update-check.service").read_text()
        self.assertIn("check all --notify", service)
        self.assertNotIn(" update ", service)
        self.assertTrue((self.home / ".config/systemd/user/desktop-update-check.timer").exists())

    def test_notifications_are_once_per_revision_and_checks_do_not_deploy(self):
        items = [dict(profile="inir", status="behind", upstream="origin/prerelease", behind=2,
                      remote_commit="revision-one"), dict(profile="nyxuri", status="error")]
        with patch.object(update.shutil, "which", return_value="notify-send"), \
                patch.object(update.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as notify:
            update.notify_updates(self.home, items)
            update.notify_updates(self.home, items)
            self.assertEqual(notify.call_count, 1)
            command = notify.call_args.args[0]
            self.assertEqual(command[:3], ["notify-send", "-a", "desktop-update"])
            self.assertIn("desktop-update update inir", command[-1])
            items[0]["remote_commit"] = "revision-two"
            update.notify_updates(self.home, items)
            self.assertEqual(notify.call_count, 2)

    def test_check_all_continues_after_one_fetch_failure(self):
        self.registry(("inir", "nyxuri"))
        result = dict(profile="nyxuri", upstream="origin/main", ahead=0, behind=1, status="behind")
        output = io.StringIO()
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(update, "report", side_effect=[ValueError("offline"), result]) as report, \
                patch.object(update, "sync") as sync, contextlib.redirect_stdout(output):
            self.assertEqual(update.main(["check", "all", "--json"]), 1)
        self.assertEqual([x["status"] for x in json.loads(output.getvalue())], ["error", "behind"])
        self.assertEqual(report.call_count, 2)
        sync.assert_not_called()

    def test_inir_gui_argument_order_uses_the_shared_pipeline(self):
        helper = self.home / ".local/bin/desktop-update"
        helper.parent.mkdir(parents=True)
        helper.write_text('#!/bin/sh\nprintf "%s\\n" "$*"\n')
        helper.chmod(0o755)
        registry = self.home / ".config/desktop-profiles/profiles.json"
        registry.parent.mkdir(parents=True)
        registry.write_text('{}')
        for args in (["-y", "update"], ["-y", "-q", "update"]):
            command = ['bash', '-c', 'source "$1" "${@:2}"', '_', str(ROOT / 'scripts/personal/setup-entry.sh'), *args]
            result = subprocess.run(command, env=dict(os.environ, HOME=str(self.home)), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'update inir')

    def test_hypr_gui_preferences_are_retained(self):
        with patch.object(update, "running", return_value=True):
            command = update.deploy_command("hyprland-ii", self.repo, no_hypr=True, no_restart=True)
        self.assertIn('--no-hypr', command)
        self.assertIn('--no-restart', command)


    def test_palette_contract_failure_prevents_backup_and_all_installers(self):
        registry = self.home / ".config/desktop-profiles/profiles.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"inir": {"source": str(self.repo)}}))
        profiles = Mock()
        profiles.verify_theme_contract.side_effect = ValueError("upstream output changed")
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(update, "check_source"), \
                patch.object(update, "checks", return_value=[]), \
                patch.object(update, "profile_manager", return_value=profiles), \
                patch.object(update, "snapshot") as backup, \
                patch.object(update.subprocess, "run") as deploy:
            with self.assertRaisesRegex(ValueError, "upstream output"):
                update.main(["deploy", "inir"])
        backup.assert_not_called()
        deploy.assert_not_called()

    def test_nyxuri_deployment_also_uses_managed_theme_maintenance(self):
        registry = self.home / ".config/desktop-profiles/profiles.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"nyxuri": {"source": str(self.repo)}}))
        profiles = Mock()
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(update, "check_source"), \
                patch.object(update, "checks", return_value=[]), \
                patch.object(update, "profile_manager", return_value=profiles), \
                patch.object(update, "snapshot"), \
                patch.object(update, "chezmoi_before", return_value={}), \
                patch.object(update.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as deploy:
            self.assertEqual(update.main(["deploy", "nyxuri"]), 0)
        profiles.verify_theme_contract.assert_called_once_with("nyxuri")
        profiles.check_theme_maintenance.assert_called_once_with("nyxuri")
        self.assertEqual(deploy.call_args.args[0][:4],
                         [str(self.home / ".local/bin/desktop-profile"), "maintain", "nyxuri", "--"])


if __name__ == "__main__":
    unittest.main()
