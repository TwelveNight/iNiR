#!/usr/bin/env python3
"""User-requested XDG autostart choices, shared by Niri and Hyprland."""
import os
from pathlib import Path
import re


DISABLED = {
    "org.kde.kgpg.desktop": ("KGpg", "kgpg"),
    "org.kde.kalendarac.desktop": ("Calendar Reminders", "kalendarac"),
    "org.kde.kclockd-autostart.desktop": ("Clock", "kclockd"),
}


def set_key(text, key, value):
    """Edit only the main desktop group; retain custom commands and actions."""
    group = re.search(r"(?m)^\[Desktop Entry\][ \t]*$", text)
    if not group:
        raise ValueError("Missing Desktop Entry group")
    next_group = re.search(r"(?m)^\[", text[group.end():])
    end = group.end() + next_group.start() if next_group else len(text)
    body = text[group.end():end]
    pattern = rf"(?m)^{re.escape(key)}=.*$"
    if re.search(pattern, body):
        body = re.sub(pattern, lambda _: f"{key}={value}", body)
    else:
        body = body.rstrip() + f"\n{key}={value}\n\n"
    return text[:group.end()] + body + text[end:]


def configure(config_home):
    directory = config_home / "autostart"
    paths = [directory / name for name in DISABLED] + [directory / "todesk.desktop"]
    if directory.is_symlink() or any(path.is_symlink() for path in paths):
        raise ValueError("Autostart entries must not redirect to other files")
    changes = {}
    for name, (label, command) in DISABLED.items():
        path = directory / name
        text = path.read_text() if path.exists() else (
            "# Personal overlay: manual launch remains available.\n"
            f"[Desktop Entry]\nType=Application\nName={label}\nExec={command}\n")
        changes[path] = set_key(text, "Hidden", "true")

    # A stale user desktop entry refers to a removed ToDesk installation.
    # Preserve its command; let XDG skip it until that binary exists again.
    todesk = directory / "todesk.desktop"
    if todesk.is_file():
        text = todesk.read_text()
        if re.search(r"(?m)^Exec=.*(?<!\S)/opt/todesk/bin/ToDesk(?:\s|$)", text):
            # This legacy entry stored its app version (4.8.1.0) here; the
            # desktop specification's Version field describes the file format.
            text = set_key(text, "Version", "1.0")
            changes[todesk] = set_key(text, "TryExec", "/opt/todesk/bin/ToDesk")

    directory.mkdir(parents=True, exist_ok=True)
    for path, text in changes.items():
        if not path.exists() or path.read_text() != text:
            path.write_text(text)


if __name__ == "__main__":
    configure(Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"))
