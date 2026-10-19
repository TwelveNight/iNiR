#!/usr/bin/env python3
"""Persist private paths for both GDM/systemd and Niri-spawned commands."""
import json
import os
from pathlib import Path
import re


def configure_portals(config_home):
    directory = config_home / "xdg-desktop-portal"
    target = directory / "niri-portals.conf"
    if directory.is_symlink() or target.is_symlink():
        raise ValueError("Niri portal config must not redirect to another desktop's files")
    template = Path(__file__).with_name("niri-portals.conf")
    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(template.read_text())


def configure_hyprland_session(config_home):
    # The personal Hyprland config already starts/stops this target. Restore
    # only a missing unit; retain any user's existing unit or service mask.
    hooks = config_home / "hypr/hyprland/execs.lua"
    target = config_home / "systemd/user/hyprland-session.target"
    if target.exists() or target.is_symlink():
        return
    if not hooks.is_file() or "hyprland-session.target" not in hooks.read_text():
        return
    if target.parent.is_symlink():
        raise ValueError("Hyprland session unit directory must not be redirected")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(Path(__file__).with_name("hyprland-session.target").read_text())


def configure_desktop_sessions(config_home):
    template_dir = Path(__file__).parent
    # Dependency directives are additive: an empty drop-in cannot remove
    # PropagatesStopTo. Migrate only our known personal target directive before
    # binding the target to the monitor.
    session_target = config_home / "systemd/user/hyprland-session.target"
    if session_target.is_symlink() or session_target.parent.is_symlink():
        raise ValueError("Hyprland session target must not be redirected")
    if session_target.exists():
        text = session_target.read_text()
        known = "PropagatesStopTo=graphical-session.target"
        for line in text.splitlines():
            if line.strip().startswith("PropagatesStopTo=") and line.strip() != known:
                raise ValueError("Unknown Hyprland stop propagation; review before binding the monitor")
        updated = "\n".join(line for line in text.splitlines() if line.strip() != known) + "\n"
        if text != updated:
            session_target.write_text(updated)
    for relative, template in (
        ("systemd/user/inir-hyprland-watch.service", "inir-hyprland-watch.service"),
        ("systemd/user/hyprland-session.target.d/40-compositor-lifetime.conf", "hyprland-session-lifetime.conf"),
        ("systemd/user/app-.service.d/40-desktop-ready.conf", "autostart-desktop-ready.conf"),
    ):
        target = config_home / relative
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError("Desktop lifecycle units must not be redirected")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((template_dir / template).read_text())
    dropin = config_home / "systemd/user/niri.service.d/30-session-environment.conf"
    if dropin.is_symlink() or dropin.parent.is_symlink():
        raise ValueError("Niri session drop-in must not be redirected")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text((template_dir / "niri-session-environment.conf").read_text())
    for unit in ("skwd-walld.service", "ii-skwd-wall-theme.service"):
        wallpaper = config_home / f"systemd/user/{unit}.d/30-desktop-session.conf"
        if wallpaper.is_symlink() or wallpaper.parent.is_symlink():
            raise ValueError("Wallpaper session drop-in must not be redirected")
        wallpaper.parent.mkdir(parents=True, exist_ok=True)
        wallpaper.write_text((template_dir / "wallpaper-session.conf").read_text())

    unit = config_home / "systemd/user/inir-output-wallpaper.service"
    if unit.is_symlink():
        raise ValueError("Wallpaper output watcher unit must not be redirected")
    unit.write_text((template_dir / "inir-output-wallpaper.service").read_text())
    wants = config_home / "systemd/user/niri.service.wants/inir-output-wallpaper.service"
    wants.parent.mkdir(parents=True, exist_ok=True)
    if not wants.exists() and not wants.is_symlink():
        wants.symlink_to("../inir-output-wallpaper.service")

    hooks = config_home / "hypr/hyprland/execs.lua"
    custom = config_home / "hypr/custom/execs.lua"
    activation = config_home / "hypr/custom/inir-session.lua"
    if not hooks.is_file() or not custom.is_file():
        return
    if any(path.is_symlink() or path.parent.is_symlink() for path in (hooks, custom, activation)):
        raise ValueError("Hyprland session hooks must not be redirected")
    text = hooks.read_text()
    # Replace only the known asynchronous environment publishers. They race
    # with shell startup, leak the other desktop's names, and never reconnect skwd.
    obsolete = [
        '    hl.exec_cmd("dbus-update-activation-environment --all")',
        '    hl.exec_cmd("sleep 1 && dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE && systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE && systemctl --user start hyprland-session.target")',
    ]
    for line in obsolete:
        text = text.replace(line + "\n", "")
    if "dbus-update-activation-environment" in text or "import-environment" in text:
        raise ValueError("Unknown Hyprland environment hook; review it before installing the session helper")
    restore = '    hl.exec_cmd("$HOME/.config/hypr/custom/scripts/__restore_video_wallpaper.sh")\n'
    if not (config_home / "hypr/custom/scripts/__restore_video_wallpaper.sh").exists():
        text = text.replace(restore, "")
    if text != hooks.read_text():
        hooks.write_text(text)
    activation.write_text((template_dir / "hyprland-session.lua").read_text())
    require = 'require("custom.inir-session")'
    custom_text = custom.read_text()
    if require not in custom_text:
        custom.write_text(custom_text.rstrip() + "\n\n-- Shared Niri/Hyprland session lifecycle.\n" + require + "\n")


def configure_personal_input(niri):
    """Wire personal input through the user-owned entry, leaving upstream intact."""
    root = niri / "config.kdl"
    if 'include "config.d/90-user-extra.kdl"' not in root.read_text():
        return
    extra = niri / "config.d/90-user-extra.kdl"
    target = niri / "config.d/95-personal-input.kdl"
    if extra.is_symlink() or target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Personal input config must not redirect to another file")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        template = Path(__file__).resolve().parents[2] / "defaults/niri/config.d/95-personal-input.kdl"
        target.write_text(template.read_text())
    text = extra.read_text() if extra.exists() else ""
    include = 'include "95-personal-input.kdl"'
    if not re.search(r'^\s*include\s+"95-personal-input\.kdl"\s*(?://.*)?$', text, re.MULTILINE):
        extra.write_text(text.rstrip() + "\n\n// Personal input preferences; keep upstream input untouched.\n" + include + "\n")


def configure_personal_games(niri):
    """Load game-specific rules after upstream, without replacing user rules."""
    root = niri / "config.kdl"
    if 'include "config.d/90-user-extra.kdl"' not in root.read_text():
        return
    extra = niri / "config.d/90-user-extra.kdl"
    target = niri / "config.d/96-personal-games.kdl"
    if extra.is_symlink() or target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Personal game config must not redirect to another file")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        template = Path(__file__).resolve().parents[2] / "defaults/niri/config.d/96-personal-games.kdl"
        target.write_text(template.read_text())
    text = extra.read_text() if extra.exists() else ""
    include = 'include "96-personal-games.kdl"'
    if not re.search(r'^\s*include\s+"96-personal-games\.kdl"\s*(?://.*)?$', text, re.MULTILINE):
        extra.write_text(text.rstrip() + "\n\n// Per-game window policy; keep upstream and launchers unchanged.\n" + include + "\n")


def configure_shell_preferences(config_dir):
    """Apply personal shell defaults only to iNiR's private configuration."""
    target = config_dir / "config.json"
    if config_dir.is_symlink() or target.is_symlink():
        raise ValueError("Personal shell config must not redirect to another desktop's files")
    options = json.loads(target.read_text()) if target.exists() else {}
    before = json.dumps(options, sort_keys=True)
    # Personal app colors follow the wallpaper, independently of iRiS's paper/accent.
    preferences = Path(__file__).resolve().parents[2] / "defaults/personal-app-theming.json"
    if preferences.is_file():
        def merge(target, values):
            for key, value in values.items():
                if isinstance(value, dict):
                    merge(target.setdefault(key, {}), value)
                else:
                    target[key] = value
        merge(options, json.loads(preferences.read_text()))
    options.setdefault("bar", {}).setdefault("weather", {})["enable"] = False
    if json.dumps(options, sort_keys=True) == before:
        return
    config_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(options, ensure_ascii=False, indent=4) + "\n")


def configure(config_home, config_dir, state_dir, venv_dir, bin_home):
    paths = {
        "INIR_CONFIG_DIR": str(config_dir),
        "INIR_STATE_DIR": str(state_dir),
        "INIR_VENV": str(venv_dir),
        "INIR_RUNTIME_DIR": str(config_home / "quickshell/inir"),
    }
    if any(not Path(value).is_absolute() or "\n" in value for value in paths.values()):
        raise ValueError("iNiR paths must be absolute, single-line paths")
    configure_shell_preferences(config_dir)
    configure_portals(config_home)
    niri = (config_home / "niri").resolve()
    # Install the separate personal layer once; preserve subsequent user edits.
    root_config = niri / "config.kdl"
    root_text = root_config.read_text()
    configure_personal_input(niri)
    configure_personal_games(niri)
    gpu_anchor = 'include "config.d/10-input-and-cursor.kdl"'
    gpu_include = 'include "config.d/05-personal-gpu.kdl"'
    if gpu_anchor in root_text:
        personal_gpu = niri / "config.d/05-personal-gpu.kdl"
        if not personal_gpu.exists():
            template = Path(__file__).resolve().parents[2] / "defaults/niri/config.d/05-personal-gpu.kdl"
            personal_gpu.write_text(template.read_text())
        if gpu_include not in root_text:
            root_text = root_text.replace(gpu_anchor, gpu_include + "\n" + gpu_anchor, 1)
    upstream_include = 'include "config.d/70-binds.kdl"'
    personal_include = 'include "config.d/75-personal-binds.kdl"'
    if upstream_include in root_text:
        personal = niri / "config.d/75-personal-binds.kdl"
        if not personal.exists():
            template = Path(__file__).resolve().parents[2] / "defaults/niri/config.d/75-personal-binds.kdl"
            personal.write_text(template.read_text())
        if personal_include not in root_text:
            root_text = root_text.replace(upstream_include,
                                         upstream_include + "\n" + personal_include, 1)
    upstream_rules = 'include "config.d/30-window-rules.kdl"'
    personal_rules_include = 'include "config.d/35-personal-window-rules.kdl"'
    if upstream_rules in root_text:
        personal_rules = niri / "config.d/35-personal-window-rules.kdl"
        if not personal_rules.exists():
            template = Path(__file__).resolve().parents[2] / "defaults/niri/config.d/35-personal-window-rules.kdl"
            personal_rules.write_text(template.read_text())
        if personal_rules_include not in root_text:
            root_text = root_text.replace(upstream_rules,
                                         upstream_rules + "\n" + personal_rules_include, 1)
    if root_config.read_text() != root_text:
        root_config.write_text(root_text)
    env_file = niri / "config.d/40-environment.kdl"
    if not env_file.is_file():
        env_file = niri / "config.kdl"
    text = env_file.read_text()
    for name in paths:
        text = re.sub(r'(?m)^\s*' + name + r'\s+"[^"\n]*"[^\n]*\n?', '', text)
    entries = "\n".join(f"    {name} {json.dumps(value, ensure_ascii=False)}" for name, value in paths.items())
    text, count = re.subn(r'(?m)^([ \t]*environment[ \t]*\{)', lambda m: m[0] + "\n" + entries, text, count=1)
    if not count:
        text += "\nenvironment {\n" + entries + "\n}\n"
    env_file.write_text(text)

    # GDM need not add ~/.local/bin to PATH; every iNiR binding has an absolute executable.
    launcher = str(bin_home / "inir")
    for binding in [niri / "config.kdl", niri / "config.d/70-binds.kdl", niri / "config.d/75-personal-binds.kdl"]:
        if binding.is_file():
            text = binding.read_text()
            text = re.sub(r'\bspawn "(?:[^"\n]*/)?inir"', lambda _: "spawn " + json.dumps(launcher), text)
            binding.write_text(text)

    dropin = config_home / "systemd/user/inir.service.d/20-personal-paths.conf"
    dropin.parent.mkdir(parents=True, exist_ok=True)
    # systemd expands specifiers even inside quoted Environment values.
    dropin.write_text("# Managed by the personal overlay installer\n[Service]\n" + "".join(
        "Environment=" + json.dumps(name + "=" + value.replace("%", "%%"), ensure_ascii=False) + "\n"
        for name, value in paths.items()))

    bridge_dropin = config_home / "systemd/user/app-org.kde.xwaylandvideobridge@autostart.service.d/20-inir-session.conf"
    bridge_dropin.parent.mkdir(parents=True, exist_ok=True)
    bridge_template = Path(__file__).with_name("xwaylandvideobridge-autostart.conf")
    bridge_dropin.write_text(bridge_template.read_text())
    configure_hyprland_session(config_home)
    configure_desktop_sessions(config_home)


if __name__ == "__main__":
    home = Path.home()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    config_dir = Path(os.environ.get("INIR_CONFIG_DIR") or config_home / "inir")
    state_dir = Path(os.environ.get("INIR_STATE_DIR") or Path(os.environ.get("XDG_STATE_HOME") or home / ".local/state") / "inir")
    venv_dir = Path(os.environ.get("INIR_VENV") or state_dir / ".venv")
    bin_home = Path(os.environ.get("XDG_BIN_HOME") or home / ".local/bin")
    configure(config_home, config_dir, state_dir, venv_dir, bin_home)
