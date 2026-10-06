#!/usr/bin/env python3
"""Exercise repair failure/backup boundaries using only temporary files."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gem_deploy", ROOT / "scripts/personal/deploy-nvidia-gem-fix.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentTests(unittest.TestCase):
    def test_initramfs_config_files_do_not_trigger_module_rebuild(self):
        self.assertFalse(deploy.contains_nvidia_module("usr/lib/modprobe.d/nvidia-utils.conf\netc/modprobe.d/nvidia-power-management.conf\n"))
        self.assertTrue(deploy.contains_nvidia_module("usr/lib/modules/kernel/updates/dkms/nvidia.ko.zst\n"))
        self.assertTrue(deploy.contains_nvidia_module("usr/lib/modules/kernel/nvidia-drm.ko\n"))
        self.assertFalse(deploy.contains_nvidia_module("usr/lib/modules/kernel/not-nvidia.ko.zst\n"))

    def test_unknown_or_user_owned_backup_cannot_restore_system_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(deploy, "BASE", base / "expected"), patch.object(deploy, "command") as command:
                with self.assertRaises(ValueError):
                    deploy.restore(base)
                command.assert_not_called()

    def fixture_install(self, directory, fail=False):
        base = Path(directory)
        source = base / "source/nvidia/nv-dma.c"
        source.parent.mkdir(parents=True)
        original = b"original driver fixture"
        repaired = b"repaired driver fixture"
        source.write_bytes(original)
        dkms = base / "dkms/nvidia"
        dkms.mkdir(parents=True)
        (dkms / "state").write_text("installed old driver")
        backups = base / "backups"
        backups.mkdir()
        old_modules = {}
        for kernel, _ in deploy.KERNELS:
            p = base / "installed" / kernel / "nvidia.ko.zst"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"old module")
            old_modules[kernel] = p
        image = base / "initramfs.img"
        image.write_bytes(b"unchanged initramfs without NVIDIA modules")
        images = [dict(path=str(image), sha256=deploy.digest(image), preset="linux-zen", contains_nvidia=False)]
        calls = []

        def command(snapshot, label, *args):
            calls.append(args)
            if args[0] == "cp":
                src, dst = Path(args[-2]), Path(args[-1])
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            elif args[:2] == ("dkms", "build") and fail:
                raise RuntimeError("compiler failure fixture")
            elif args[:2] == ("dkms", "install"):
                old_modules[args[args.index("-k") + 1]].write_bytes(b"new compiled module")

        def output(*args):
            if args[0] == "modinfo":
                if args[2] == "version":
                    return deploy.VERSION
                return Path(args[-1]).parent.name + " SMP preempt mod_unload"
            if args[0] == "dkms":
                return "\n".join(f"nvidia/{deploy.VERSION}, {kernel}, x86_64: installed" for kernel, _ in deploy.KERNELS)
            raise AssertionError(args)

        def patch_source(*args, **kwargs):
            self.assertEqual(args[0][0], "patch")
            # Simulate applying the independently compiler-validated patch.
            self.assertTrue((next(p for p in backups.iterdir() if p.is_dir()) / "manifest.json").exists())
            source.write_bytes(repaired)
            return subprocess.CompletedProcess(args, 0)

        overrides = dict(BASE=backups, SOURCE=source, DKMS=dkms, MODULES=("nvidia",),
                         ORIGINAL=__import__('hashlib').sha256(original).hexdigest(),
                         PATCHED=__import__('hashlib').sha256(repaired).hexdigest(),
                         command=command, output=output, module_files=lambda kernel: [old_modules[kernel]])
        with patch.multiple(deploy, **overrides), patch.object(deploy.subprocess, "run", patch_source), patch.object(deploy, "restore") as restore:
            if fail:
                with self.assertRaises(RuntimeError):
                    deploy.install(images)
                restore.assert_called_once()
                self.assertFalse(any(c[:2] == ("dkms", "install") for c in calls))
            else:
                deploy.install(images)
                restore.assert_not_called()
                state = json.loads((backups / "status.json").read_text())
                self.assertEqual(state["phase"], "installed_pending_reboot")
                self.assertEqual(state["regenerated_presets"], [])
                self.assertEqual(deploy.digest(image), images[0]["sha256"])
                self.assertFalse(any(c[0] in ("mkinitcpio", "modprobe", "rmmod", "reboot") for c in calls))
        return calls

    def test_compile_failure_requests_rollback_before_installing_any_module(self):
        with tempfile.TemporaryDirectory() as directory:
            self.fixture_install(directory, fail=True)

    def test_success_backs_up_modules_and_keeps_current_session_and_initramfs(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = self.fixture_install(directory)
            builds = [i for i,c in enumerate(calls) if c[:2] == ("dkms", "build")]
            installs = [i for i,c in enumerate(calls) if c[:2] == ("dkms", "install")]
            self.assertLess(max(builds), min(installs))

    def test_dkms_override_is_valid_for_actual_export_and_array_semantics(self):
        directive = "MAKE='make' -j4 IGNORE_PREEMPT_RT_PRESENCE=1 KERNEL_UNAME=fixture-kernel modules"
        result = subprocess.check_output(["bash", "-ec", 'make() { printf "%s\\n" "$@"; }; MAKE=(old); export "$1"; eval "${MAKE[0]}"', "fixture", directive], text=True)
        self.assertEqual(result.splitlines(), ["-j4", "IGNORE_PREEMPT_RT_PRESENCE=1", "KERNEL_UNAME=fixture-kernel", "modules"])


if __name__ == "__main__":
    unittest.main()
