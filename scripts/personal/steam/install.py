#!/usr/bin/env python3
"""Install the Niri-only Steam GTK2 workaround without editing Steam/runtime files."""
from pathlib import Path
import datetime
import os
import shutil
import subprocess
import tempfile


def install():
    source = Path(__file__).resolve().parent
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    state = Path(os.environ.get('INIR_STATE_DIR') or Path.home() / '.local/state/inir')
    bindir = Path(os.environ.get('XDG_BIN_HOME') or Path.home() / '.local/bin')
    directory = data / 'inir/steam'
    desktop = data / 'applications/steam.desktop'
    executable = bindir / 'steam'
    template = Path('/usr/share/applications/steam.desktop')
    if not template.exists():
        raise SystemExit('Steam desktop entry is not installed')
    for target, marker in ((desktop, '# inir-steam-randr-guard'), (executable, '# inir-steam-randr-guard')):
        if target.exists() and marker not in target.read_text():
            raise SystemExit(f'Existing custom entry needs review: {target}')
    with tempfile.TemporaryDirectory() as temp:
        built = Path(temp) / 'gtk2-randr-guard.so'
        subprocess.run(['gcc', '-m32', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-Wl,-z,relro,-z,now', str(source / 'gtk2-randr-guard.c'), '-ldl', '-o', str(built)], check=True)
        backup = state / 'backups' / ('steam-randr-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True)
        targets = (directory / built.name, desktop, executable)
        for i, target in enumerate(targets):
            if target.exists(): shutil.copy2(target, backup / f'{i}-{target.name}')
        (backup / 'paths.txt').write_text('\n'.join(map(str, targets)) + '\n')
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, directory / built.name)
        bindir.mkdir(parents=True, exist_ok=True)
        # A stable launcher resolves the current live source after updates.
        executable.write_text('#!/bin/sh\n# inir-steam-randr-guard\nexec "${XDG_CONFIG_HOME:-$HOME/.config}/quickshell/inir/scripts/personal/steam/steam-niri.sh" "$@"\n')
        executable.chmod(0o755)
        desktop.parent.mkdir(parents=True, exist_ok=True)
        quoted = '"' + str(executable).replace('\\', '\\\\').replace('"', '\\"') + '"'
        text = template.read_text().replace('Exec=/usr/bin/steam', 'Exec=' + quoted)
        desktop.write_text('# inir-steam-randr-guard\n' + text)
        subprocess.run(['update-desktop-database', str(desktop.parent)], check=True)
        print(f'Steam guard installed; backup: {backup}')


if __name__ == '__main__':
    install()
