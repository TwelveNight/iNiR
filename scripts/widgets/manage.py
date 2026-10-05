#!/usr/bin/env python3
"""Manage direct child widgets with validated names, without shell evaluation."""
import json
from pathlib import Path
import re
import shutil
import sys

DEFAULTS = Path(__file__).resolve().parents[2] / "defaults/widgets"
# scripts/widgets/manage.py -> repo root is parents[2].
ID = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}\Z")


def widget_path(root, name):
    if not ID.fullmatch(name):
        raise ValueError("Widget ID must start with a letter and contain only letters, digits, _ or -")
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Widget root must be an absolute directory, not a symlink")
    path = root / name
    if path.is_symlink():
        raise ValueError("Refusing a symlinked widget")
    return path


def scan(root):
    result = []
    if not root.is_dir() or root.is_symlink():
        return result
    for directory in sorted(root.iterdir()):
        if not ID.fullmatch(directory.name) or directory.is_symlink() or not directory.is_dir():
            continue
        manifest = directory / "widget.json"
        if manifest.is_symlink():
            continue
        try:
            value = json.loads(manifest.read_text())
            if not isinstance(value, dict):
                continue
            main = value.get("main") or directory.name[0].upper() + directory.name[1:] + ".qml"
            iris = value.get("iris") or {}
            if not isinstance(iris, dict):
                continue
            for entry in [main, iris.get("main")]:
                if not entry:
                    continue
                file = Path(entry)
                if file.is_absolute() or ".." in file.parts or not (directory / file).resolve().is_relative_to(directory.resolve()):
                    raise ValueError("Widget entry escapes its directory")
        except (OSError, ValueError, TypeError):
            continue
        result.append({"id": directory.name, "dir": str(directory), "manifest": value})
    return result


def main():
    action, raw_root, *names = sys.argv[1:]
    root = Path(raw_root)
    if action == "scan":
        print(json.dumps(scan(root)))
        return
    name, = names
    target = widget_path(root, name)
    if action == "remove":
        if target.exists():
            shutil.rmtree(target)
        print("removed")
        return
    if action not in {"create", "example"}:
        raise ValueError("Unknown widget operation")
    # Never overwrite a widget, even when create is triggered twice.
    root.mkdir(parents=True, exist_ok=True)
    if action == "example":
        shutil.copytree(DEFAULTS / "example-widget", target, symlinks=True)
    else:
        class_name = "".join(part[0].upper() + part[1:] for part in re.split(r"[-_]+", name) if part)
        payload = {}
        for source, dest in [("widget.json.in", "widget.json"), ("Widget.qml.in", class_name + ".qml"),
                             ("IrisCompact.qml.in", "IrisCompact.qml")]:
            text = (DEFAULTS / "scaffold" / source).read_text()
            payload[dest] = text.replace("@WIDGET_CLASS@", class_name).replace("@WIDGET_ID@", name)
        target.mkdir()  # Fails for existing directories and links.
        for dest, text in payload.items():
            (target / dest).write_text(text)
    print("done")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Widget operation refused: {error}", file=sys.stderr)
        raise SystemExit(2)
