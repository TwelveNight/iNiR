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


def main(command):
    if command == "empty-move":
        empty_workspace(True)
    elif command == "empty-focus":
        empty_workspace()
    elif command == "float":
        toggle_float()
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
        main(sys.argv[1])
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Niri personal action: {error}", file=sys.stderr)
        sys.exit(1)
