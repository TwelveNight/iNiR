#!/usr/bin/env python3
"""Read-only dependency report for the personal skwd/GDM overlay.

Never invokes a package installation, refresh, replacement or service change.
Arch checks use pacman -T so installed alternative providers remain valid.
"""
import json
import shutil
import subprocess
import sys


# (command, Arch package or external provider, capability)
REQUIRED_COMMANDS = [
    ("skwd-helm", "existing skwd-wall", "shared wallpaper backend"),
    ("niri", "niri", "compositor"), ("qs", "existing Quickshell provider", "Shell runtime"),
    ("jq", "jq", "settings"), ("rsync", "rsync", "deployment and backups"),
    ("uv", "uv", "private Python environment"), ("python3", "python", "helpers"),
    ("systemctl", "systemd", "session lifecycle"), ("matugen", "matugen", "shared colors"),
    ("swayidle", "swayidle", "idle and suspend"),
    ("swaylock", "swaylock", "fallback when the Shell cannot secure the session"),
    ("wl-copy", "wl-clipboard", "clipboard"), ("wl-paste", "wl-clipboard", "clipboard"),
    ("cliphist", "cliphist", "shared history"), ("ffmpeg", "ffmpeg", "media helpers"),
    ("magick", "imagemagick", "image helpers"), ("socat", "socat", "media IPC"),
    ("nmcli", "networkmanager", "network controls"), ("wpctl", "wireplumber", "audio controls"),
    ("secret-tool", "libsecret", "shared keyring"), ("fish", "fish", "runtime scripts"),
    ("curl", "curl", "network helpers"), ("git", "git", "maintenance"),
    ("flock", "util-linux", "serialized writes"),
    ("setpriv", "util-linux", "wallpaper listener lifecycle"),
    ("notify-send", "libnotify", "helper notifications"),
    ("kbuildsycoca6", "kservice", "Niri startup application index"),
    ("xdg-open", "xdg-utils", "open files and URLs"),
    ("xwayland-satellite", "xwayland-satellite", "X11 applications"),
]

# QML modules and native prerequisites for the private Python requirements.
REQUIRED_PACKAGES = [
    "qt6-base", "qt6-declarative", "qt6-wayland", "qt6-svg", "qt6-5compat",
    "qt6-multimedia", "qt6-imageformats", "qt6-quicktimeline", "kirigami",
    "syntax-highlighting", "xdg-desktop-portal", "xdg-desktop-portal-gnome",
    "xdg-desktop-portal-gtk", "pipewire", "polkit", "gnome-keyring",
    "cairo", "gobject-introspection", "python-gobject", "pkgconf", "base-devel",
]

OPTIONAL_COMMANDS = [
    ("brightnessctl", "brightnessctl", "backlight"), ("ddcutil", "ddcutil", "external monitor brightness"),
    ("wlsunset", "wlsunset", "night light"), ("cava", "cava", "visualizer"),
    ("qalc", "libqalculate", "calculator"), ("bluetoothctl", "bluez-utils", "Bluetooth"),
    ("blueman-manager", "blueman", "Bluetooth settings"),
    ("grim", "grim", "screenshots"), ("slurp", "slurp", "region selection"),
    ("swappy", "swappy", "annotation"), ("wf-recorder", "wf-recorder", "recording"),
    ("tesseract", "tesseract", "OCR"), ("trans", "translate-shell", "translation"),
    ("songrec", "songrec", "song recognition"), ("hyprpicker", "hyprpicker", "color picker"),
    ("mpv", "mpv", "media playback"), ("deno", "deno", "YouTube extraction JS runtime"),
    ("playerctl", "playerctl", "media control"), ("easyeffects", "easyeffects", "audio effects"),
    ("missioncenter", "mission-center", "default system monitor"),
    ("nm-connection-editor", "nm-connection-editor", "network editor"),
    ("pavucontrol", "pavucontrol", "audio mixer"), ("kitty", "kitty", "default terminal"),
    ("fuzzel", "fuzzel", "fallback launcher"), ("nautilus", "nautilus", "default file manager"),
]
OPTIONAL_PACKAGES = {
    "plasma-integration": "KDE Qt platform theme (qt6ct fallback available)",
    "plasma-browser-integration": "browser MPRIS integration; browser extension also needed",
    "lsp-plugins-lv2": "native EasyEffects equalizer backend",
    "mpv-mpris": "mpv MPRIS integration", "ttf-oxanium": "alternate Shell typography",
    "ttf-roboto-flex": "default UI typography", "ttf-gabarito-git": "default title typography",
    "ttf-material-symbols-variable": "Shell icon font", "noto-fonts-emoji": "emoji",
    "tesseract-data-eng": "English OCR", "tesseract-data-chi_sim": "Simplified Chinese OCR",
    "tesseract-data-spa": "Spanish OCR", "tesseract-data-rus": "Russian OCR",
    "tesseract-data-jpn": "Japanese OCR", "tesseract-data-jpn_vert": "vertical Japanese OCR",
    "tesseract-data-chi_sim_vert": "vertical Simplified Chinese OCR",
    "tesseract-data-chi_tra": "Traditional Chinese OCR",
    "tesseract-data-chi_tra_vert": "vertical Traditional Chinese OCR",
}


def check():
    report = {"required": [], "optional": [], "errors": []}
    for level, entries in [("required", REQUIRED_COMMANDS), ("optional", OPTIONAL_COMMANDS)]:
        for command, package, purpose in entries:
            if not shutil.which(command):
                report[level].append({"item": command, "package": package, "purpose": purpose})
    if shutil.which("pacman"):
        for level, packages in [("required", dict.fromkeys(REQUIRED_PACKAGES, "runtime/native dependency")),
                                ("optional", OPTIONAL_PACKAGES)]:
            result = subprocess.run(["pacman", "-T", *packages], capture_output=True, text=True)
            if result.returncode not in (0, 127):
                report["errors"].append("Could not inspect the local pacman dependency database")
                continue
            for package in result.stdout.splitlines():
                if package not in packages:
                    report["errors"].append("Unexpected pacman dependency result")
                    continue
                report[level].append({"item": package, "package": package, "purpose": packages[package]})
    else:
        report["errors"].append("Native/QML package checks currently require Arch pacman; verify them manually")
    agents = ["/usr/lib/polkit-kde-authentication-agent-1", "/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1",
              "/usr/lib/mate-polkit/polkit-mate-authentication-agent-1", "lxqt-policykit-agent", "lxpolkit"]
    if not any(shutil.which(agent) for agent in agents):
        report["required"].append({"item": "polkit-agent", "package": "polkit-gnome", "purpose": "GUI authentication"})
    return report


def main():
    report = check()
    if "--json" in sys.argv[1:]:
        print(json.dumps(report, indent=2))
    else:
        for level, label in [("required", "Missing required"), ("optional", "Missing optional feature")]:
            for entry in report[level]:
                print(f"{label}: {entry['item']} [{entry['package']}] — {entry['purpose']}")
        for error in report["errors"]:
            print(error, file=sys.stderr)
        if not report["required"] and not report["errors"]:
            print("Required overlay dependencies are available; optional entries above limit those features only.")
        print("Read-only check: preserve the existing Quickshell provider; install missing packages separately.")
    return int(bool(report["required"] or report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
