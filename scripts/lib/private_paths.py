"""Validate private iNiR paths before lifecycle operations can write or delete."""
import os
from pathlib import Path
import sys


def overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def validate(environment=None):
    env = os.environ if environment is None else environment
    home = Path(env.get("HOME", str(Path.home())))
    config = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    state = Path(env.get("XDG_STATE_HOME") or home / ".local/state")
    cache = Path(env.get("XDG_CACHE_HOME") or home / ".cache")
    data = Path(env.get("XDG_DATA_HOME") or home / ".local/share")
    private_config = Path(env.get("INIR_CONFIG_DIR") or env.get("DOTS_CORE_CONFDIR") or config / "inir")
    private_state = Path(env.get("INIR_STATE_DIR") or state / "inir")
    venv = Path(env.get("INIR_VENV") or private_state / ".venv")
    runtime = config / "quickshell/inir"
    targets = [private_config, private_state, venv, runtime, cache / "inir",
               private_config / "config.json", private_config / "widgets", private_state / "user"]
    targets += [private_state / name for name in ("backups", "install-backups", "snapshots")]
    if env.get("INIR_RUNTIME_DIR"):
        targets.append(Path(env["INIR_RUNTIME_DIR"]))
    if runtime.is_symlink():
        raise ValueError("Installed Shell directory must not be a symlink")
    if env.get("DOTS_CORE_CONFDIR") and Path(env["DOTS_CORE_CONFDIR"]).resolve() != private_config.resolve():
        raise ValueError("DOTS_CORE_CONFDIR and INIR_CONFIG_DIR disagree")
    for path in [home, config, state, cache, data, *targets]:
        if not path.is_absolute() or any(ord(c) < 32 for c in str(path)):
            raise ValueError("iNiR paths must be absolute and contain no control characters")
    # Compare both logical names and resolved aliases, including shared II
    # directories themselves linked into a dotfiles checkout.
    protected = [config / "illogical-impulse", config / "quickshell/ii", state / "quickshell",
                 cache / "quickshell", home / ".ssh", home / ".gnupg", data / "chezmoi"]
    protected += [config / name for name in ("hypr", "niri", "kitty", "fish", "systemd", "gtk-3.0",
                                             "gtk-4.0", "qt5ct", "qt6ct", "Kvantum", "cliphist")]
    roots = [home, config, state, cache, data]
    for target in targets:
        for candidate in [target.absolute(), target.resolve()]:
            if any(candidate == root.resolve() or candidate in root.resolve().parents for root in roots):
                raise ValueError(f"Refusing broad private path: {target}")
            if any(overlap(candidate, alias) for root in protected for alias in [root.absolute(), root.resolve()]):
                raise ValueError(f"Refusing private path overlapping II/shared data: {target}")
    if overlap(private_config.resolve(), private_state.resolve()) or overlap(private_config.resolve(), venv.resolve()):
        raise ValueError("Private settings, state and Python environment must not overlap settings")
    if venv.resolve() == private_state.resolve() or venv.resolve() in private_state.resolve().parents:
        raise ValueError("Python environment must not contain the state directory")
    if any(overlap(runtime.resolve(), path.resolve()) for path in [private_config, private_state, venv]):
        raise ValueError("Shell code must not overlap settings, state or the Python environment")


if __name__ == "__main__":
    try:
        validate()
        if "--runtime-links" in sys.argv[1:]:
            runtime = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "quickshell/inir"
            for path in runtime.rglob("*"):
                if path.is_symlink() and not path.resolve().is_relative_to(runtime.resolve()):
                    raise ValueError(f"Installed runtime link escapes its directory: {path}")
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Unsafe iNiR paths: {error}", file=sys.stderr)
        raise SystemExit(2)
