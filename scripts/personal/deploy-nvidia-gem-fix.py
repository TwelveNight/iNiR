#!/usr/bin/env python3
"""Explicit, version-bound NVIDIA repair; never invoked by ./setup install."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

VERSION = "615.71.09"
ORIGINAL = "0382ba885442f2ca457a661b0e33a847732bf81f9a71034674c8489e28ca2536"
PATCHED = "6779e8039181d5a88b4871071caf34ce9054f2da79de490c7f9aa77e3fa74e0c"
PATCH_HASH = "70260deda7eaa325333721ea0bd0d86c3d020d621bfe9bcc80f4aad1989c5ae1"
KERNELS = (("7.2.8-zen1-2-zen", "linux-zen"), ("6.18.55-1-lts", "linux-lts"))
MODULES = ("nvidia", "nvidia-uvm", "nvidia-modeset", "nvidia-drm", "nvidia-peermem")
SOURCE = Path(f"/usr/src/nvidia-{VERSION}/nvidia/nv-dma.c")
DKMS = Path("/var/lib/dkms/nvidia")
BASE = Path("/var/lib/inir/nvidia-gem-owner")
PATCH = Path(__file__).with_name("patches") / "nvidia-615.71.09-gem-owner.patch"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def output(*command):
    return subprocess.check_output(command, text=True).strip()


def contains_nvidia_module(listing):
    names = "|".join(re.escape(name) for name in MODULES)
    return bool(re.search(r"(?m)(?:^|/)(?:" + names + r")\.ko(?:\.(?:zst|xz|gz))?$", listing))


def preflight():
    if socket.gethostname() != "nightArch" or os.uname().machine != "x86_64":
        raise ValueError("This repair is bound to nightArch x86_64")
    if digest(SOURCE) != ORIGINAL or digest(PATCH) != PATCH_HASH:
        raise ValueError("Driver source or patch changed; review before installing")
    if output("modinfo", "-F", "version", "nvidia") != VERSION:
        raise ValueError("Installed NVIDIA version changed")
    if Path("/sys/module/nvidia/version").read_text().strip() != VERSION:
        raise ValueError("Loaded NVIDIA version changed")
    if Path("/var/lib/pacman/db.lck").exists():
        raise ValueError("A package transaction is in progress")
    installed = output("dkms", "status", "-m", "nvidia", "-v", VERSION)
    images = []
    for kernel, preset in KERNELS:
        if f"nvidia/{VERSION}, {kernel}, x86_64: installed" not in installed:
            raise ValueError(f"Expected installed DKMS kernel is missing: {kernel}")
        if not Path(f"/usr/lib/modules/{kernel}/build/Makefile").is_file():
            raise ValueError(f"Kernel headers missing: {kernel}")
        for suffix in ("", "-fallback"):
            image = Path(f"/boot/initramfs-{preset}{suffix}.img")
            if not image.is_file() or image.is_symlink():
                raise ValueError(f"Unexpected boot image: {image}")
            images.append(dict(path=str(image), sha256=digest(image),
                               preset=preset, contains_nvidia=contains_nvidia_module(output("lsinitcpio", str(image)))))
    if shutil.disk_usage("/var/lib").free < 2 * 1024 ** 3:
        raise ValueError("Insufficient space for module backups and builds")
    return images


def command(snapshot, label, *args):
    print(label, flush=True)
    log = snapshot / "commands.log"
    with log.open("ab") as stream:
        stream.write(("\n$ " + " ".join(args) + "\n").encode())
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{label} failed (exit {result.returncode}); log: {log}")


def module_files(kernel):
    directory = Path(f"/usr/lib/modules/{kernel}/updates/dkms")
    files = []
    for name in MODULES:
        matches = [p for p in directory.glob(name + ".ko*") if p.is_file()]
        if len(matches) != 1 or matches[0].is_symlink():
            raise ValueError(f"Expected one installed {name} module for {kernel}")
        files.append(matches[0])
    return files


def save_report(snapshot, phase, **extra):
    report = dict(phase=phase, version=VERSION, backup=str(snapshot),
                  timestamp=datetime.now().astimezone().isoformat(), **extra)
    (snapshot / "status.json").write_text(json.dumps(report, indent=2) + "\n")
    public = BASE / "status.json"
    temporary = BASE / "status.json.tmp"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.chmod(0o644)
    os.replace(temporary, public)


def restore(snapshot):
    snapshot = snapshot.resolve(strict=True)
    if snapshot.parent != BASE or snapshot.stat().st_uid != 0:
        raise ValueError("Rollback requires an original root-owned repair backup")
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if manifest["version"] != VERSION or manifest["kernels"] != [k for k, _ in KERNELS]:
        raise ValueError("Backup version or kernel scope does not match this repair")
    # Restore exactly the recorded source, module files and NVIDIA DKMS state.
    command(snapshot, "Restoring driver source", "cp", "-a", str(snapshot / "nv-dma.c"), str(SOURCE))
    for kernel, _ in KERNELS:
        for module in MODULES:
            for path in Path(f"/usr/lib/modules/{kernel}/updates/dkms").glob(module + ".ko*"):
                path.unlink()
        for filename in manifest["modules"][kernel]:
            source = snapshot / "modules" / kernel / filename
            target = Path(f"/usr/lib/modules/{kernel}/updates/dkms") / filename
            command(snapshot, f"Restoring {kernel}/{filename}", "cp", "-a", str(source), str(target))
    if DKMS.exists():
        shutil.rmtree(DKMS)
    command(snapshot, "Restoring NVIDIA DKMS state", "cp", "-a", str(snapshot / "dkms-nvidia"), str(DKMS))
    for image in manifest["images"]:
        command(snapshot, f"Restoring {image['path']}", "cp", "-a", str(snapshot / "boot" / Path(image["path"]).name), image["path"])
    for kernel, _ in KERNELS:
        command(snapshot, f"Restoring module indexes for {kernel}", "depmod", "-a", kernel)
    if digest(SOURCE) != ORIGINAL:
        raise RuntimeError("Restored source hash mismatch")
    for kernel, hashes in manifest["modules"].items():
        for filename, expected in hashes.items():
            if digest(Path(f"/usr/lib/modules/{kernel}/updates/dkms") / filename) != expected:
                raise RuntimeError(f"Restored module hash mismatch: {kernel}/{filename}")
    for image in manifest["images"]:
        if digest(Path(image["path"])) != image["sha256"]:
            raise RuntimeError("Restored boot image hash mismatch")
    save_report(snapshot, "rolled_back")
    print("Rollback complete. The loaded driver was not unloaded.", flush=True)


def install(images):
    snapshot = BASE / ("backup-" + datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}")
    snapshot.mkdir(mode=0o700)
    print(f"Backup: {snapshot}", flush=True)
    manifest = dict(version=VERSION, kernels=[k for k, _ in KERNELS], modules={}, images=images,
                    boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())
    command(snapshot, "Backing up driver source", "cp", "-a", str(SOURCE), str(snapshot / "nv-dma.c"))
    command(snapshot, "Backing up NVIDIA DKMS state", "cp", "-a", str(DKMS), str(snapshot / "dkms-nvidia"))
    for kernel, _ in KERNELS:
        target = snapshot / "modules" / kernel
        target.mkdir(parents=True)
        manifest["modules"][kernel] = {}
        for path in module_files(kernel):
            manifest["modules"][kernel][path.name] = digest(path)
            command(snapshot, f"Backing up {kernel}/{path.name}", "cp", "-a", str(path), str(target / path.name))
    (snapshot / "boot").mkdir()
    for image in images:
        command(snapshot, f"Backing up {image['path']}", "cp", "-a", image["path"], str(snapshot / "boot" / Path(image["path"]).name))
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    save_report(snapshot, "backed_up")
    mutated = False
    try:
        # Do not trust a source edit made since the backup began.
        if digest(SOURCE) != ORIGINAL or Path("/var/lib/pacman/db.lck").exists():
            raise ValueError("Source/package state changed during backup")
        mutated = True
        with PATCH.open("rb") as stream, (snapshot / "commands.log").open("ab") as log:
            subprocess.run(["patch", "--batch", "--forward", "-p1", "-d", str(SOURCE.parents[1])],
                           stdin=stream, stdout=log, stderr=subprocess.STDOUT, check=True)
        if digest(SOURCE) != PATCHED:
            raise ValueError("Patched source hash mismatch")
        for kernel, _ in KERNELS:
            command(snapshot, f"Building patched driver for {kernel}", "dkms", "build", "--force", "-m", "nvidia", "-v", VERSION, "-k", kernel,
                    "-j", "4", "--directive", f"MAKE='make' -j4 IGNORE_PREEMPT_RT_PRESENCE=1 KERNEL_UNAME={kernel} modules")
        for kernel, _ in KERNELS:
            command(snapshot, f"Installing driver files for {kernel}", "dkms", "install", "--force", "-m", "nvidia", "-v", VERSION, "-k", kernel)
            for path in module_files(kernel):
                if output("modinfo", "-F", "version", str(path)) != VERSION:
                    raise ValueError(f"Installed module version mismatch: {path}")
                if not output("modinfo", "-F", "vermagic", str(path)).startswith(kernel + " "):
                    raise ValueError(f"Installed module vermagic mismatch: {path}")
                if digest(path) == manifest["modules"][kernel][path.name] and path.name.startswith("nvidia.ko"):
                    raise ValueError("Core NVIDIA module was not rebuilt")
        # The current images contain modprobe configuration, but no NVIDIA .ko.
        # Only regenerate presets that actually embed a replaced driver module.
        rebuild = sorted({image["preset"] for image in images if image["contains_nvidia"]})
        for preset in rebuild:
            command(snapshot, f"Regenerating {preset} initramfs", "mkinitcpio", "-p", preset)
        for image in images:
            if image["preset"] not in rebuild and digest(Path(image["path"])) != image["sha256"]:
                raise ValueError("An unrelated initramfs changed during installation")
        installed = output("dkms", "status", "-m", "nvidia", "-v", VERSION)
        for kernel, _ in KERNELS:
            if f"nvidia/{VERSION}, {kernel}, x86_64: installed" not in installed:
                raise ValueError(f"DKMS did not confirm installed state: {kernel}")
        new_hashes = {kernel: {p.name: digest(p) for p in module_files(kernel)} for kernel, _ in KERNELS}
        save_report(snapshot, "installed_pending_reboot", source_sha256=digest(SOURCE), module_hashes=new_hashes,
                    regenerated_presets=rebuild, boot_id=manifest["boot_id"])
        print("Installed for Zen and LTS. Reboot is required to load the repaired driver; no reboot was requested.", flush=True)
    except BaseException:
        if not mutated:
            save_report(snapshot, "aborted_before_changes")
            raise
        print("Installation failed; restoring original files.", file=sys.stderr, flush=True)
        try:
            restore(snapshot)
        except BaseException as rollback_error:
            save_report(snapshot, "rollback_failed", error=str(rollback_error))
            print(f"Rollback needs attention: {rollback_error}", file=sys.stderr, flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "install", "rollback"))
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.action == "check":
        images = preflight()
        print(json.dumps(dict(version=VERSION, kernels=[k for k, _ in KERNELS], images=images), indent=2))
        return
    if os.geteuid() != 0:
        raise PermissionError("Use sudo or the system authorization dialog; do not send a password to chat")
    os.umask(0o077)
    os.environ["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/bin"
    os.environ["LC_ALL"] = "C"
    BASE.mkdir(parents=True, mode=0o755, exist_ok=True)
    if BASE.is_symlink() or BASE.stat().st_uid != 0:
        raise ValueError("Repair backup directory must be root-owned and not redirected")
    BASE.chmod(0o755)
    lockfd = os.open(str(BASE / "repair.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lockfd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "rollback":
            if not args.backup:
                parser.error("rollback requires --backup")
            if output("modinfo", "-F", "version", "nvidia") != VERSION or digest(SOURCE) not in (ORIGINAL, PATCHED):
                raise ValueError("Driver upgraded or changed since repair; do not roll back across versions")
            restore(args.backup)
        else:
            install(preflight())


if __name__ == "__main__":
    main()
