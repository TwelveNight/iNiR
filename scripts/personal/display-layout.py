#!/usr/bin/env python3
"""Place this laptop's HDMI left of eDP-2 without moving the remote origin."""
from difflib import unified_diff
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

spec = importlib.util.spec_from_file_location('niri_config', Path(__file__).parents[1] / 'niri-config.py')
kdl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kdl)


def position_outputs(text, width=2560):
    if width <= 0:
        raise ValueError('HDMI logical width must be positive')
    for name, x in [('HDMI-A-1', -width), ('eDP-2', 0)]:
        bounds = kdl._find_output_block_bounds(text, name)
        if bounds is None:
            continue
        _, start, end, _ = bounds
        block = kdl._set_in_block(text[start:end], 'position', f'x={x} y=0')
        text = text[:start] + block + text[end:]
    return text


def apply(root, width=2560, check=False):
    root = Path(root).resolve()
    originals = {p: p.read_text() for p in [root / 'monitor.kdl', root / 'config.kdl'] if p.is_file()}
    if root / 'config.kdl' not in originals:
        raise ValueError('Missing Niri config.kdl')
    updated = {p: position_outputs(text, width) for p, text in originals.items()}
    with tempfile.TemporaryDirectory(prefix='inir-display-layout-') as temporary:
        candidate = Path(temporary) / 'niri'
        shutil.copytree(root, candidate, ignore=shutil.ignore_patterns('backups'))
        for path, text in updated.items():
            (candidate / path.name).write_text(text)
        subprocess.run(['niri', 'validate', '-c', str(candidate / 'config.kdl')], check=True)
    changes = {p: text for p, text in updated.items() if text != originals[p]}
    for path, text in changes.items():
        print(''.join(unified_diff(originals[path].splitlines(True), text.splitlines(True),
                                   fromfile=str(path), tofile=str(path))), end='')
    if check or not changes:
        return
    for path in changes:
        if path.read_text() != originals[path]:
            raise RuntimeError('Configuration changed during validation')
    backup = root / 'backups' / ('display-layout-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    for path in changes:
        shutil.copy2(path, backup / path.name)
    try:
        for path, text in changes.items():
            fd, temporary = tempfile.mkstemp(prefix='.layout-', suffix='.kdl', dir=root)
            try:
                with os.fdopen(fd, 'w') as stream:
                    stream.write(text)
                os.chmod(temporary, path.stat().st_mode & 0o777)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        subprocess.run(['niri', 'validate', '-c', str(root / 'config.kdl')], check=True)
    except BaseException:
        for path in changes:
            shutil.copy2(backup / path.name, path)
        raise
    print('Backup:', backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config/desktop-profiles/inir/niri')
    parser.add_argument('--hdmi-width', type=int, default=2560, help='HDMI logical width after scaling')
    parser.add_argument('--check', action='store_true', help='Validate and display changes without writing')
    args = parser.parse_args()
    apply(args.config_dir, args.hdmi_width, args.check)
