#!/usr/bin/env python3
"""Route both GNOME Secret Service activation names to the same user service."""
import os
from pathlib import Path


def configure(data_home):
    directory = data_home / "dbus-1/services"
    names = ("org.freedesktop.secrets", "org.gnome.keyring")
    if any(path.is_symlink() for path in (directory, directory.parent)) or any(
            (directory / (name + ".service")).is_symlink() for name in names):
        raise ValueError("Keyring activation files must not be redirected")
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / (name + ".service")).write_text(
            "# Personal overlay: keep D-Bus and socket activation on one daemon.\n"
            f"[D-BUS Service]\nName={name}\n"
            "Exec=/usr/bin/gnome-keyring-daemon --start --foreground --components=secrets\n"
            "SystemdService=gnome-keyring-daemon.service\n")


if __name__ == "__main__":
    configure(Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"))
