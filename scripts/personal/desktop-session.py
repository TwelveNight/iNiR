#!/usr/bin/env python3
"""Publish a compositor's environment and retire its shared wallpaper clients."""
import argparse
from contextlib import nullcontext
import fcntl
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess

# Neither systemd nor D-Bus drops names omitted by import-environment.
IDENTITY = ("WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP",
            "XDG_SESSION_DESKTOP", "NIRI_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE")
GPU = ("AQ_DRM_DEVICES", "WLR_NO_HARDWARE_CURSORS", "WLR_DRM_NO_ATOMIC",
       "LIBVA_DRIVER_NAME", "__GL_VRR_ALLOWED", "DRI_PRIME",
       "__NV_PRIME_RENDER_OFFLOAD", "__GLX_VENDOR_LIBRARY_NAME",
       "__VK_LAYER_NV_optimus", "__EGL_VENDOR_LIBRARY_FILENAMES",
       "VK_LOADER_DRIVERS_DISABLE", "MESA_VK_DEVICE_SELECT",
       "MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE", "VDPAU_DRIVER",
       "QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "INIR_SHELL_GPU_PREFERENCE")
TOOLKIT = ("QT_QPA_PLATFORM", "QT_QPA_PLATFORMTHEME", "XDG_MENU_PREFIX",
           "XCURSOR_THEME", "XCURSOR_SIZE", "HYPRCURSOR_THEME", "HYPRCURSOR_SIZE",
           "GTK_IM_MODULE", "QT_IM_MODULE", "SDL_IM_MODULE", "XMODIFIERS")


def run(*args, env=None):
    return subprocess.run(args, env=env, check=True, capture_output=True, text=True)


def session_identity(desktop, env):
    runtime = Path(env["XDG_RUNTIME_DIR"])
    display = env.get("WAYLAND_DISPLAY", "")
    wayland = Path(display) if display.startswith("/") else runtime / display
    if not display or not wayland.is_socket():
        raise ValueError("The current Wayland socket is not ready")
    key = "NIRI_SOCKET" if desktop == "niri" else "HYPRLAND_INSTANCE_SIGNATURE"
    value = env.get(key, "")
    if not value:
        raise ValueError(f"Missing {key}; run from the compositor's startup hook")
    ipc = Path(value) if desktop == "niri" else runtime / "hypr" / value / ".socket.sock"
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(3)
        peer.connect(str(ipc))
        pid, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    expected = "niri" if desktop == "niri" else "Hyprland"
    if uid != os.getuid() or Path(f"/proc/{pid}/comm").read_text().strip() != expected:
        raise ValueError("IPC peer is not the current user's compositor")
    return dict(desktop=desktop, pid=pid, key=key, value=value, wayland=display)


def publish_environment(desktop, env):
    env = dict(env)
    # A prior D-Bus handoff can leave empty placeholders in the login process.
    # Treat empty GPU selectors as absent, or they get re-imported into systemd
    # after our unset-environment call. An empty FFmpeg list is intentional.
    for name in GPU:
        if name != "QT_FFMPEG_DECODING_HW_DEVICE_TYPES" and env.get(name) == "":
            env.pop(name)
    env["XDG_CURRENT_DESKTOP"] = "niri" if desktop == "niri" else "Hyprland"
    env["XDG_SESSION_DESKTOP"] = env["XDG_CURRENT_DESKTOP"]
    opposite = ("HYPRLAND_INSTANCE_SIGNATURE", "AQ_DRM_DEVICES",
                "WLR_NO_HARDWARE_CURSORS", "WLR_DRM_NO_ATOMIC",
                "__GL_VRR_ALLOWED", "LIBVA_DRIVER_NAME", "HYPRCURSOR_THEME", "HYPRCURSOR_SIZE") if desktop == "niri" else (
                    "NIRI_SOCKET", "INIR_SHELL_GPU_PREFERENCE",
                    "__NV_PRIME_RENDER_OFFLOAD", "__VK_LAYER_NV_optimus")
    for name in opposite:
        env.pop(name, None)
    names = IDENTITY + GPU + TOOLKIT
    missing = [name for name in names if name not in env]
    # D-Bus cannot unset variables: clear missing names explicitly, then import
    # only present names into systemd. Never publish Shell-only Mesa overrides.
    run("dbus-update-activation-environment",
        *(f"{name}={env.get(name, '')}" for name in names))
    # dbus-broker can mirror even the non --systemd update into systemd.
    # Remove empty placeholders afterward; GLVND/Mesa distinguish unset from "".
    if missing:
        run("systemctl", "--user", "unset-environment", *missing)
    present = [name for name in names if name in env]
    run("systemctl", "--user", "import-environment", *present, env=env)


def manager_owns(identity):
    values = dict(line.split("=", 1) for line in
                  run("systemctl", "--user", "show-environment").stdout.splitlines() if "=" in line)
    desktop = values.get("XDG_CURRENT_DESKTOP", "")
    expected = "niri" if identity["desktop"] == "niri" else "Hyprland"
    if desktop and desktop != expected:
        return False
    if (values.get(identity["key"]) == identity["value"]
            and values.get("WAYLAND_DISPLAY") == identity["wayland"]):
        return True
    # niri-session may clear its identity before this watcher gets scheduled.
    # The lock/state still belongs to this exited compositor; finish cleanup
    # only when no newer desktop has published an identity/display.
    return not any(values.get(name) for name in
                   ("NIRI_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY"))


def unit_active(unit):
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit],
                          capture_output=True).returncode == 0


def retire(identity):
    # A watcher for an old session must never stop a newer session's wallpaper.
    if not manager_owns(identity):
        return
    run("systemctl", "--user", "stop", "ii-skwd-wall-theme.service", "skwd-walld.service")
    if identity["desktop"] == "hyprland":
        run("systemctl", "--user", "stop", "hyprland-session.target")
    run("dbus-update-activation-environment", *(f"{name}=" for name in IDENTITY + GPU + TOOLKIT))
    run("systemctl", "--user", "unset-environment", *(IDENTITY + GPU + TOOLKIT))
    print(f"desktop-session: retired {identity['desktop']} pid={identity['pid']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "watch"))
    parser.add_argument("desktop", choices=("niri", "hyprland"))
    parser.add_argument("--identity", help=argparse.SUPPRESS)
    parser.add_argument("--adopt", action="store_true", help="Monitor the live session without restarting its wallpaper")
    args = parser.parse_args()
    env = dict(os.environ)
    directory = Path(env["XDG_RUNTIME_DIR"]) / "inir"
    directory.mkdir(mode=0o700, exist_ok=True)
    state = directory / "desktop-session.json"
    identity = json.loads(args.identity) if args.action == "watch" else session_identity(args.desktop, env)
    # Open the pidfd before publishing any state; it also prevents PID reuse.
    try:
        fd = os.fdopen(os.pidfd_open(identity["pid"]), "rb", buffering=0)
    except ProcessLookupError:
        if args.action != "watch":
            raise
        fd = None  # The compositor may exit before systemd launches the watcher.
    with fd if fd is not None else nullcontext() as pidfd:
        if args.action == "watch" and pidfd is not None:
            select.select([pidfd], [], [])
        with (directory / "desktop-session.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.action == "watch":
                if state.exists() and json.loads(state.read_text()) == identity:
                    retire(identity)
                    state.unlink()
                return
            if select.select([pidfd], [], [], 0)[0]:
                raise ValueError("Compositor exited before session activation")
            watcher = f"inir-desktop-watch-{identity['pid']}.service"
            watch_active = unit_active(watcher)
            if state.exists() and json.loads(state.read_text()) == identity:
                if watch_active and unit_active("skwd-walld.service") and not args.adopt:
                    return
            publish_environment(args.desktop, env)
            if not watch_active:
                run("systemd-run", "--user", "--collect",
                    f"--unit={watcher}", "--property=Slice=background.slice",
                    "/usr/bin/python3", str(Path(__file__).resolve()), "watch", args.desktop,
                    "--identity", json.dumps(identity))
            state.write_text(json.dumps(identity) + "\n")
            if args.desktop == "hyprland":
                run("systemctl", "--user", "start", "hyprland-session.target")
            if not args.adopt:
                run("systemctl", "--user", "restart", "skwd-walld.service")
                config = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
                if (config / "quickshell/ii/scripts/colors/skwd-wall-theme-listener.sh").is_file():
                    run("systemctl", "--user", "restart", "ii-skwd-wall-theme.service")
            print(f"desktop-session: activated {args.desktop} pid={identity['pid']} wayland={identity['wayland']}", flush=True)


if __name__ == "__main__":
    main()
