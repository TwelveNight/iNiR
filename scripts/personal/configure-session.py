#!/usr/bin/env python3
"""Persist private paths for both GDM/systemd and Niri-spawned commands."""
import json
import os
from pathlib import Path
import re


def configure(config_home, config_dir, state_dir, venv_dir, bin_home):
    paths = {
        "INIR_CONFIG_DIR": str(config_dir),
        "INIR_STATE_DIR": str(state_dir),
        "INIR_VENV": str(venv_dir),
        "INIR_RUNTIME_DIR": str(config_home / "quickshell/inir"),
    }
    if any(not Path(value).is_absolute() or "\n" in value for value in paths.values()):
        raise ValueError("iNiR paths must be absolute, single-line paths")
    niri = config_home / "niri"
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
    for binding in [niri / "config.kdl", niri / "config.d/70-binds.kdl"]:
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


if __name__ == "__main__":
    home = Path.home()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    config_dir = Path(os.environ.get("INIR_CONFIG_DIR") or config_home / "inir")
    state_dir = Path(os.environ.get("INIR_STATE_DIR") or Path(os.environ.get("XDG_STATE_HOME") or home / ".local/state") / "inir")
    venv_dir = Path(os.environ.get("INIR_VENV") or state_dir / ".venv")
    bin_home = Path(os.environ.get("XDG_BIN_HOME") or home / ".local/bin")
    configure(config_home, config_dir, state_dir, venv_dir, bin_home)
