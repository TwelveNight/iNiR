#!/usr/bin/env python3
"""Personal shortcuts implemented with Niri IPC, never Hyprland scripts."""
import json
import os
import shutil
import socket
import subprocess
import sys


def query(name):
    return json.loads(subprocess.check_output(["niri", "msg", "--json", name], text=True))


def action(name, *args):
    subprocess.run(["niri", "msg", "action", name, *map(str, args)], check=True)


def request_action(value):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(os.environ["NIRI_SOCKET"])
        client.sendall((json.dumps({"Action": value}) + "\n").encode())
        with client.makefile("r") as stream:
            response = json.loads(stream.readline(65536))
    if "Ok" not in response:
        raise RuntimeError(f"Niri rejected action: {response}")


def empty_workspace(move=False):
    workspaces = query("workspaces")
    current = next((w for w in workspaces if w.get("is_focused")), None)
    if current is None:
        return
    # Niri always keeps a trailing empty workspace on each output. Use its
    # stable ID rather than an index that may change when a workspace empties.
    target = max((w for w in workspaces if w["output"] == current["output"]),
                 key=lambda w: w["idx"])
    occupied = {w["workspace_id"] for w in query("windows")}
    if target["id"] in occupied:
        raise RuntimeError("Trailing workspace is not empty; refusing to move")
    window = query("focused-window") if move else None
    if move and window is None:
        return
    request = {"MoveWindowToWorkspace": {
        "window_id": window["id"], "reference": {"Id": target["id"]}, "focus": True,
    }} if move else {"FocusWorkspace": {"reference": {"Id": target["id"]}}}
    request_action(request)


def toggle_float():
    window = query("focused-window")
    if not window:
        return
    window_id = window["id"]
    if window["is_floating"]:
        action("move-window-to-tiling", "--id", window_id)
        return
    action("move-window-to-floating", "--id", window_id)
    action("set-window-width", "--id", window_id, "50%")
    action("set-window-height", "--id", window_id, "60%")
    action("center-window", "--id", window_id)


def toggle_hud_focus():
    windows = query("windows")
    hud = next((w for w in windows if w.get("app_id") == "hermes"
                and w.get("title") == "Hermes HUD"), None)
    if hud is None:
        return
    target = hud
    if hud.get("is_focused"):
        # Niri's focus history survives HUD recreation and never holds closed ids.
        candidates = [w for w in windows if w["id"] != hud["id"]
                      and not (w.get("app_id") == "hermes"
                               and w.get("title") == "Hermes Pet Overlay")]
        def recent(window):
            timestamp = window.get("focus_timestamp") or {}
            return timestamp.get("secs", 0), timestamp.get("nanos", 0)
        target = max(candidates, key=recent, default=None)
    if target is not None:
        action("focus-window", "--id", target["id"])


def bus_call(*args):
    result = subprocess.check_output([
        "busctl", "--user", "--json=short", "--timeout=2", *map(str, args),
    ], text=True, timeout=3)
    return json.loads(result)["data"] if result.strip() else []


def hide_folia(window_id):
    window = next((w for w in query("windows") if w["id"] == int(window_id)), None)
    if window is None:
        return
    if window.get("app_id") != "folia-major" or window.get("title") != "Folia":
        raise RuntimeError("Refusing to hide a window other than the Folia player")
    pid = window.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeError("Folia window has no valid process ID")
    dbus = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")
    names = bus_call("call", *dbus, "ListNames")[0]
    services = [name for name in names
                if name.startswith(f"org.freedesktop.StatusNotifierItem-{pid}-")]
    if len(services) != 1:
        raise RuntimeError("Cannot identify Folia's tray; leaving the player running")
    # Pin the unique owner so a restarted/replaced service cannot receive the event.
    owner = bus_call("call", *dbus, "GetNameOwner", "s", services[0])[0]
    if bus_call("call", *dbus, "GetConnectionUnixProcessID", "s", owner)[0] != pid:
        raise RuntimeError("Folia tray process does not match the captured window")
    menu = bus_call("get-property", owner, "/StatusNotifierItem",
                    "org.kde.StatusNotifierItem", "Menu")
    target = (owner, menu, "com.canonical.dbusmenu")
    layout = bus_call("call", *target, "GetLayout", "iias", 0, 1, 3,
                      "label", "enabled", "visible")
    hide_labels = {"隐藏窗口", "Hide Window", "Sembunyikan Jendela"}
    show_labels = {"显示窗口", "Show Window", "Tampilkan Jendela"}
    for item in layout[1][2]:
        item_id, properties, _children = item["data"]
        label = properties.get("label", {}).get("data")
        if label in show_labels:
            return  # Already hidden: repeated requests must not toggle it back open.
        if label in hide_labels:
            if (not properties.get("enabled", {}).get("data", True)
                    or not properties.get("visible", {}).get("data", True)):
                break
            bus_call("call", *target, "Event", "isvu", item_id, "clicked", "s", "", 0)
            return
    # Never replace a failed tray operation with a close request.
    raise RuntimeError("Folia's hide menu is unavailable; leaving the player running")


def main(command, *args):
    if command == "empty-move":
        empty_workspace(True)
    elif command == "empty-focus":
        empty_workspace()
    elif command == "float":
        toggle_float()
    elif command == "hud-focus":
        toggle_hud_focus()
    elif command == "folia-hide":
        hide_folia(args[0])
    elif command == "tmux":
        # Uses the shared Kitty config and the most recently used tmux session.
        exists = subprocess.run(["tmux", "has-session"], capture_output=True).returncode == 0
        os.execvp("kitty", ["kitty", "tmux", "attach-session" if exists else "new-session"])
    elif command == "files":
        for app in ["dolphin", "nautilus", "nemo", "thunar"]:
            if shutil.which(app):
                os.execvp(app, [app])
        raise RuntimeError("No file manager is available")
    else:
        raise ValueError(f"Unknown personal action: {command}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except (IndexError, KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Niri personal action: {error}", file=sys.stderr)
        sys.exit(1)
