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
import tempfile

POLICY = {
    "inir": ("snowarch/iNiR", "prerelease"),
    "hyprland-ii": ("P3DROVFX/ii-p3drovfx", "dev"),
    "nyxuri": ("ech678/Nyxuri", "main"),
    "vitreus": ("natepayn3/Vitreus", "main"),
}
BRANCH = "night/personal-overlay"


def run(command, cwd=None, capture=False, raw=False, **kwargs):
    result = subprocess.run([str(arg) for arg in command], cwd=cwd, check=True,
                            text=True, stdout=subprocess.PIPE if capture else None, **kwargs)
    return (result.stdout if raw else result.stdout.strip()) if capture else ""


def git(source, *args):
    return run(["git", "-C", source, *args], capture=True)


def overlay_branch(name):
    return "personal-overlay" if name == "vitreus" else BRANCH


def conflict_help(name, source):
    message = (f"{name}: 上游合并冲突，live 未更新。请在 {source} 打开 AI，"
               f"修复 git status 中的冲突并 git commit，再运行 desktop-update update {name}。"
               "取消合并可运行 git merge --abort。")
    if shutil.which("notify-send"):
        try:
            subprocess.run(["notify-send", "-a", "desktop-update", "-u", "critical",
                            f"{name} 更新需要 AI 修复", message], timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return message


def check_source(name, source, clean=True):
    branch = overlay_branch(name)
    if git(source, "branch", "--show-current") != branch:
        raise ValueError(f"{name}: switch {source} to {branch}")
    slug, _ = POLICY[name]
    allowed = {f"https://github.com/{slug}.git", f"git@github.com:{slug}.git"}
    if git(source, "remote", "get-url", "origin") not in allowed:
        raise ValueError(f"{name}: origin must be the official {slug} repository")
    if not clean:
        return  # Checks can report new upstream commits while local work is in progress.
    for operation in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD"):
        path = Path(git(source, "rev-parse", "--git-path", operation))
        if not path.is_absolute():
            path = source / path
        if path.exists():
            if operation == "MERGE_HEAD" and git(source, "diff", "--name-only", "--diff-filter=U"):
                raise ValueError(conflict_help(name, source))
            raise ValueError(f"{name}: finish or abort the existing Git operation first")
    if git(source, "status", "--porcelain"):
        raise ValueError(f"{name}: commit or save working tree changes before maintenance")


def fetch(name, source):
    _, branch = POLICY[name]
    # Explicit destination also works when a clone has a restricted fetch refspec.
    run(["git", "-C", source, "fetch", "--no-tags", "origin",
         f"+refs/heads/{branch}:refs/remotes/origin/{branch}"],
        timeout=60, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    return git(source, "rev-parse", f"origin/{branch}")


def report(name, source, refresh=False):
    check_source(name, source, clean=False)
    if refresh:
        fetch(name, source)
    _, branch = POLICY[name]
    ahead, behind = map(int, git(source, "rev-list", "--left-right", "--count",
                                f"HEAD...origin/{branch}").split())
    return dict(profile=name, source=str(source), branch=overlay_branch(name),
                upstream=f"origin/{branch}", ahead=ahead, behind=behind,
                status="behind" if behind else "current",
                local_commit=git(source, "rev-parse", "HEAD"),
                remote_commit=git(source, "rev-parse", f"origin/{branch}"))


def notify_updates(home, reports):
    if not shutil.which("notify-send"):
        return
    path = home / ".local/state/desktop-profiles/update-notified.json"
    seen = json.loads(path.read_text()) if path.exists() else {}
    changed = False
    for item in reports:
        name, revision = item["profile"], item.get("remote_commit")
        if item.get("status") != "behind" or seen.get(name) == revision:
            continue
        result = subprocess.run(["notify-send", "-a", "desktop-update", f"{name} 有上游更新",
                                 f"{item['upstream']} 有 {item['behind']} 个新提交。"
                                 f"运行 desktop-update update {name}；冲突时会提示打开 AI 修复。"],
                                timeout=5, capture_output=True)
        if result.returncode == 0:
            seen[name] = revision
            changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            json.dump(seen, stream)
        os.replace(stream.name, path)


def sync(name, source):
    check_source(name, source)
    _, branch = POLICY[name]
    revision = fetch(name, source)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run(["git", "-C", source, "update-ref", f"refs/desktop-updates/{stamp}", "HEAD"])
    try:
        run(["git", "-C", source, "merge", "--no-edit", revision])
    except subprocess.CalledProcessError:
        if git(source, "diff", "--name-only", "--diff-filter=U"):
            raise ValueError(conflict_help(name, source)) from None
        raise
    print(f"{name}: upstream merged; personal commits retained", flush=True)


def checks(name, source):
    if name == "vitreus":
        return [["python3", "-B", source / "personal/update.py", "verify"]]
    if name == "inir":
        return [["python3", source / "scripts/test-personal-overlay.py"],
                ["python3", source / "scripts/test-runtime-payload.py"],
                ["python3", source / "scripts/test-supervisor-reconciliation.py"],
                ["python3", "-m", "unittest", "discover", "-s", "scripts/personal/remote-desktop", "-q"]]
    if name == "hyprland-ii":
        return [["python3", source / "scripts/test-desktop-profiles.py"],
                ["python3", source / "scripts/test-quickshell-install-boundary.py"]]
    return [["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]]


def deploy_command(name, source, no_hypr=False, no_restart=False):
    if name == "vitreus":
        return ["python3", "-B", source / "personal/install.py", "--apply"]
    if name == "inir":
        return [str(source / "setup"), "update", "--local", "-y"]
    if name == "hyprland-ii":
        options = [] if running("Hyprland") and not no_restart else ["--no-restart"]
        if no_hypr:
            options.append("--no-hypr")
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
    if name in ("nyxuri", "vitreus") or not shutil.which("chezmoi"):
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
    if name == "vitreus":
        paths.append(home / ".config/desktop-profiles/vitreus-wm")
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
    parser.add_argument("action", choices=("status", "check", "sync", "verify", "deploy", "update"))
    parser.add_argument("profile", choices=(*POLICY, "vitreus-wm", "all"))
    parser.add_argument("--json", action="store_true", help="machine-readable status/check output")
    parser.add_argument("--notify", action="store_true", help="notify once per new upstream revision (check only)")
    parser.add_argument("--plan", action="store_true", help="print commands without fetching or writing")
    parser.add_argument("--no-hypr", action="store_true", help="keep existing Hyprland compositor files")
    parser.add_argument("--no-restart", action="store_true", help="do not restart the II shell")
    args = parser.parse_args(argv)
    home = Path.home()
    registry = json.loads((home / ".config/desktop-profiles/profiles.json").read_text())
    names = [name for name in POLICY if name in registry] if args.profile == "all" else ["vitreus" if args.profile == "vitreus-wm" else args.profile]
    if args.notify and args.action != "check":
        parser.error("--notify requires check")
    if args.json and args.action not in ("status", "check"):
        parser.error("--json requires status or check")
    sources = {name: Path(registry[name]["source"]) for name in names}
    reports = []
    for name, source in sources.items():
        if args.action in ("status", "check"):
            try:
                reports.append(report(name, source, refresh=args.action == "check" and not args.plan))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                if args.profile != "all":
                    raise
                reports.append(dict(profile=name, status="error", reason=str(error)))
            if not args.json:
                item = reports[-1]
                print(f"{name}: {item['upstream']} behind={item['behind']} ahead={item['ahead']}"
                      if item["status"] != "error" else f"{name}: check failed: {item['reason']}")
        else:
            check_source(name, source, clean=not args.plan)
            print(f"{name}: {source} [{overlay_branch(name)}] <- origin/{POLICY[name][1]}", flush=True)
        if args.plan:
            print("  deploy: " + repr(deploy_command(name, source, args.no_hypr, args.no_restart)))
    if args.json:
        print(json.dumps(reports if args.profile == "all" else reports[0]))
    if args.notify and not args.plan:
        notify_updates(home, reports)
    if args.plan or args.action in ("status", "check"):
        return int(any(item["status"] == "error" for item in reports))
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
        profiles = profile_manager(home)
        for name in names:
            if name != "vitreus":
                profiles.verify_theme_contract(name)
        if args.action in ("deploy", "update"):
            manager = home / ".local/bin/desktop-profile"
            # Check all palette contracts and sessions before the first write.
            # Nyxuri also needs theme routing during offline deployment.
            for name in names:
                if name == "vitreus":
                    # Its own installer checks both profile transactions and refuses
                    # to replace an active Vitreus runtime.
                    journal = home / ".local/state/desktop-profiles/theme-session/journal.json"
                    if journal.exists() and json.loads(journal.read_text()).get("profile") in ("vitreus", "vitreus-wm"):
                        raise ValueError("请先退出 Vitreus/Vitreus WM，再更新这两套 live 配置；源码合并已保留。")
                    continue
                profiles.links(name)
                profiles.check_theme_maintenance(name)
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
                command = deploy_command(name, source, args.no_hypr, args.no_restart)
                if name != "vitreus":
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
        print(f"desktop-update stopped: {error}\nNo later deployment was run.", file=sys.stderr)
        raise SystemExit(1)
