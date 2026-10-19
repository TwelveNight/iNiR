#!/usr/bin/env python3
"""Merge upstream into personal overlays, verify, then deploy installed profiles."""
import argparse
from datetime import datetime
import fcntl
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

POLICY = {
    "inir": ("snowarch/iNiR", "prerelease"),
    "hyprland-ii": ("P3DROVFX/ii-p3drovfx", "dev"),
    "nyxuri": ("ech678/Nyxuri", "main"),
}
BRANCH = "night/personal-overlay"


def run(command, cwd=None, capture=False, raw=False):
    result = subprocess.run([str(arg) for arg in command], cwd=cwd, check=True,
                            text=True, stdout=subprocess.PIPE if capture else None)
    return (result.stdout if raw else result.stdout.strip()) if capture else ""


def git(source, *args):
    return run(["git", "-C", source, *args], capture=True)


def check_source(name, source, clean=True):
    if git(source, "branch", "--show-current") != BRANCH:
        raise ValueError(f"{name}: switch {source} to {BRANCH}")
    if clean and git(source, "status", "--porcelain"):
        raise ValueError(f"{name}: commit or save working tree changes before maintenance")
    slug, _ = POLICY[name]
    allowed = {f"https://github.com/{slug}.git", f"git@github.com:{slug}.git"}
    if git(source, "remote", "get-url", "origin") not in allowed:
        raise ValueError(f"{name}: origin must be the official {slug} repository")
    for operation in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD"):
        path = Path(git(source, "rev-parse", "--git-path", operation))
        if not path.is_absolute():
            path = source / path
        if path.exists():
            raise ValueError(f"{name}: finish or abort the existing Git operation first")


def sync(name, source):
    check_source(name, source)
    _, branch = POLICY[name]
    run(["git", "-C", source, "fetch", "origin", branch])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run(["git", "-C", source, "update-ref", f"refs/desktop-updates/{stamp}", "HEAD"])
    run(["git", "-C", source, "merge", "--no-edit", f"origin/{branch}"])
    print(f"{name}: upstream merged; personal commits retained", flush=True)


def checks(name, source):
    if name == "inir":
        return [["python3", source / "scripts/test-personal-overlay.py"],
                ["python3", source / "scripts/test-runtime-payload.py"],
                ["python3", "-m", "unittest", "discover", "-s", "scripts/personal/remote-desktop", "-q"]]
    if name == "hyprland-ii":
        return [["python3", source / "scripts/test-desktop-profiles.py"],
                ["python3", source / "scripts/test-quickshell-install-boundary.py"]]
    return [["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]]


def deploy_command(name, source):
    if name == "inir":
        return [str(source / "setup"), "update", "--local", "-y"]
    if name == "hyprland-ii":
        options = [] if running("Hyprland") else ["--no-restart"]
        return [str(source / "setup-ii-p3drovfx.sh"), "update", "--local", str(source),
                "--keep-config", "--yes", *options]
    return [str(source / "nyxuri/launcher.sh"), "update", "--local", "--yes"]


def running(comm):
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            try:
                if path.stat().st_uid == os.getuid() and (path / "comm").read_text().strip() == comm:
                    return True
            except OSError:
                pass
    return False


def profile_manager(home):
    path = home / ".local/lib/desktop-profiles/desktop_profiles.py"
    spec = importlib.util.spec_from_file_location("installed_desktop_profiles", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Profiles(home)


def chezmoi_before(home, name):
    if name == "nyxuri" or not shutil.which("chezmoi"):
        return {}
    root = home / ".config/desktop-profiles" / name
    managed = run(["chezmoi", "managed", "--path-style", "absolute", "--include", "files", root], capture=True)
    result = {}
    for raw in managed.splitlines():
        path = Path(raw)
        if path.is_file() and not path.is_symlink() and path.is_relative_to(root):
            result[path] = (path.read_bytes(), run(["chezmoi", "cat", path], capture=True, raw=True))
    return result


def chezmoi_after(before):
    changed = [path for path, (data, _) in before.items() if path.is_file() and path.read_bytes() != data]
    for path in changed:
        data, desired = before[path]
        if data.decode(errors="replace") != desired or run(["chezmoi", "cat", path], capture=True, raw=True) != desired:
            raise ValueError(f"Live deployed, but chezmoi has independent edits: {path}. Review before re-add/apply.")
    if changed:
        run(["chezmoi", "re-add", "--", *changed])
        run(["chezmoi", "apply", "--", *changed])
        print(f"chezmoi: synchronized {len(changed)} files changed by this deployment", flush=True)


def snapshot(home, name):
    root = home / ".local/state/desktop-profiles/updates" / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + name)
    root.mkdir(parents=True, mode=0o700)
    paths = [home / ".config/desktop-profiles" / name]
    if name in ("inir", "hyprland-ii"):
        shell = "inir" if name == "inir" else "ii"
        paths += [home / ".config/quickshell" / shell]
    for path in paths:
        if path.exists():
            shutil.copytree(path, root / path.relative_to(home), symlinks=True)
    (root / "README.txt").write_text(
        "Installed files before deployment. Restore only this profile and its shell, from a TTY.\n"
        "Keep the canonical ~/.config links owned by desktop-profile.\n")
    print(f"Backup: {root}", flush=True)
    return root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "sync", "verify", "deploy", "update"))
    parser.add_argument("profile", choices=(*POLICY, "all"))
    parser.add_argument("--plan", action="store_true", help="print commands without fetching or writing")
    args = parser.parse_args(argv)
    home = Path.home()
    registry = json.loads((home / ".config/desktop-profiles/profiles.json").read_text())
    names = list(POLICY) if args.profile == "all" else [args.profile]
    sources = {name: Path(registry[name]["source"]) for name in names}
    for name, source in sources.items():
        check_source(name, source)
        print(f"{name}: {source} [{BRANCH}] <- origin/{POLICY[name][1]}", flush=True)
        if args.action == "status":
            print("  upstream behind/ahead: " + git(source, "rev-list", "--left-right", "--count", f"origin/{POLICY[name][1]}...HEAD"))
        if args.plan:
            print("  deploy: " + repr(deploy_command(name, source)))
    if args.plan or args.action == "status":
        return 0
    state = home / ".local/state/desktop-profiles"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "update.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action in ("sync", "update"):
            for name, source in sources.items():
                sync(name, source)
        # All selected sources must pass before the first live write.
        for name, source in sources.items():
            for command in checks(name, source):
                run(command, cwd=source)
        if args.action in ("deploy", "update"):
            manager = home / ".local/bin/desktop-profile"
            profiles = profile_manager(home)
            # iNiR and Hypr installers consume canonical paths. Preflight every
            # guard before writing any profile. Nyxuri only writes its entity.
            for name in names:
                if name != "nyxuri":
                    profiles.links(name)
                    profiles.check_change(name)
            for name, source in sources.items():
                before = chezmoi_before(home, name)
                snapshot(home, name)
                if name == "inir":
                    run(["bash", source / "scripts/personal/install-desktop-update.sh"])
                env = dict(os.environ, DESKTOP_UPDATE_LOCAL="1")
                runtime = Path(f"/run/user/{os.getuid()}")
                if (runtime / "bus").is_socket():
                    env.setdefault("XDG_RUNTIME_DIR", str(runtime))
                    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
                command = deploy_command(name, source)
                if name != "nyxuri":
                    command = [str(manager), "maintain", name, "--", *command]
                subprocess.run(command, cwd=source, env=env, check=True)
                chezmoi_after(before)
                check_source(name, source)
                print(f"{name}: deployed", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"desktop-update stopped: {error}\nNo later deployment was run. Resolve any merge conflict, commit it, then run desktop-update verify/deploy.", file=sys.stderr)
        raise SystemExit(1)
