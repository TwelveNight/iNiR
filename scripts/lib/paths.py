"""Private Shell settings; application palettes deliberately remain shared."""
import os
from pathlib import Path


def config_dir() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return Path(os.environ.get("INIR_CONFIG_DIR") or root / "inir")


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return Path(os.environ.get("INIR_STATE_DIR") or root / "inir")


def temp_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "inir"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "inir" / "tmp"


def theme_template_output(raw_path: str) -> Path:
    """Honor XDG roots and stage legacy GTK templates before color merging."""
    path = Path(os.path.abspath(os.path.expanduser(raw_path)))
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    state = Path(os.environ.get("XDG_STATE_HOME") or home / ".local/state")
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    for default, actual in [(home / ".config", config), (home / ".local/state", state),
                            (home / ".local/share", data)]:
        if path.is_relative_to(default):
            path = actual / path.relative_to(default)
            break
    if os.environ.get("INIR_INSTALL_SHARED_APP_CONFIGS", "false") != "true":
        for version in (3, 4):
            if path == config / f"gtk-{version}.0/gtk.css":
                return state / f"quickshell/user/generated/gtk-{version}-rendered.css"
    return path
