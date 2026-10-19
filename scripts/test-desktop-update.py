#!/usr/bin/env python3
"""Exercise upstream integration and failed-deploy boundaries in temporary repos."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

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
            self.assertEqual(command[-2:], ["origin", "prerelease"])
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
        with patch.object(update, "run", side_effect=self.no_network), self.assertRaises(subprocess.CalledProcessError):
            update.sync("inir", self.repo)
        self.assertTrue((self.repo / ".git/MERGE_HEAD").is_file())
        self.assertIn("<<<<<<<", (self.repo / "base").read_text())

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


if __name__ == "__main__":
    unittest.main()
