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
