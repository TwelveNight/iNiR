#!/usr/bin/env python3
"""Back up and install the shared controller without changing capture credentials."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parent
PAYLOAD = ('desktop_backend.py', 'remote_panel.py', 'inner_moonlight.py', 'wait_inner_ready.py',
           'install.py', 'README.md') + tuple(sorted(p.name for p in SOURCE.glob('test_*.py')))
LID_CONFIG = ('// Managed by the shared remote-desktop controller.\n'
              'debug {\n    // remote-panel-managed: keep-laptop-panel-on-when-lid-is-closed\n}\n')
CONTROLLER_UNIT = '''[Unit]
Description=Connection-scoped internal screen for the active desktop
After=wayvnc-campus.service
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/.local/libexec/remote-panel/remote_panel.py
Restart=on-failure
RestartSec=3
# Let the main process finish layout restoration before killing children.
KillMode=mixed
TimeoutStopSec=60
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=graphical-session.target
'''
GRACEFUL_DROPIN = '''[Service]
# SIGTERM only the manager; its in-flight probes must finish during cleanup.
KillMode=mixed
TimeoutStopSec=60
'''
CAPTURE_DROPIN = '''# Capture always follows eDP-2 on the active compositor.
[Unit]
Description=Authenticated WayVNC for the active desktop internal screen

[Service]
ExecStart=
ExecStart=%h/.local/libexec/wayvnc-uinput/wayvnc -D -C %h/.config/wayvnc/config -o eDP-2 -r -R -f 60 -L info -S %t/wayvnc-campus.sock
'''


def profile_changes(home):
    home = Path(home)
    profiles = home / '.config/desktop-profiles'
    registry = json.loads((profiles / 'profiles.json').read_text())
    changes = {}
    for name, entry in registry.items():
        if not name or '/' in name or name in ('.', '..'):
            raise ValueError('Invalid desktop profile name')
        if entry['compositor'] != 'niri':
            continue
        root = profiles / name / 'niri'
        if root.resolve() != root.absolute():
            raise ValueError('Profile storage must be an ordinary directory')
        main = (root / 'config.kdl').read_text()
        if name == 'inir':
            anchor = root / 'config.d/90-user-extra.kdl'
            include = 'include "../remote-panel__custom__.kdl"'
            if 'include "config.d/90-user-extra.kdl"' not in main:
                raise ValueError('iNiR personal entry is not included')
        else:
            anchor = root / '__custom__.kdl'
            include = 'include "remote-panel__custom__.kdl"'
            if 'include optional=true "__custom__.kdl"' not in main and 'include "__custom__.kdl"' not in main:
                raise ValueError('No preserved custom entry in profile: ' + name)
        text = anchor.read_text() if anchor.exists() else ''
        if include not in text.splitlines():
            changes[anchor] = text.rstrip() + '\n\n// Shared remote desktop lid policy.\n' + include + '\n'
        managed = root / 'remote-panel__custom__.kdl'
        if not managed.exists():
            changes[managed] = LID_CONFIG
        elif managed.read_text().count('remote-panel-managed') != 1:
            raise ValueError('Ambiguous managed lid-policy file: ' + str(managed))
    return changes


def validate_profiles(home, changes):
    profiles = Path(home) / '.config/desktop-profiles'
    registry = json.loads((profiles / 'profiles.json').read_text())
    for name, entry in registry.items():
        if entry['compositor'] != 'niri':
            continue
        root = profiles / name / 'niri'
        with tempfile.TemporaryDirectory(prefix='remote-desktop-validate-') as directory:
            candidate = Path(directory) / 'niri'
            shutil.copytree(root, candidate, ignore=shutil.ignore_patterns('backups', '__pycache__'))
            for path, text in changes.items():
                if path.is_relative_to(root):
                    target = candidate / path.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text)
            subprocess.run(['niri', 'validate', '-c', str(candidate / 'config.kdl')], check=True)


def assert_idle(env):
    clients = json.loads(subprocess.check_output(
        ['wayvncctl', '-S', env['XDG_RUNTIME_DIR'] + '/wayvnc-campus.sock', '--json', 'client-list'], env=env, text=True))
    if clients:
        raise RuntimeError('A remote VNC client is connected; installation would interrupt it')
    for unit in ('app-dev.lizardbyte.app.Sunshine.service', 'moonlight-inner.service'):
        pid = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], env=env, text=True).strip()
        if pid != '0':
            raise RuntimeError('Remote streaming/preparation is running: ' + unit)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix='.remote-install-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(home, apply=False):
    home = Path(home)
    env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
    env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + env['XDG_RUNTIME_DIR'] + '/bus'
    changes = profile_changes(home)
    validate_profiles(home, changes)
    payload = {path: text.encode() for path, text in changes.items()}
    destination = home / '.local/libexec/remote-panel'
    payload.update({destination / name: (SOURCE / name).read_bytes() for name in PAYLOAD})
    units = home / '.config/systemd/user'
    payload[units / 'remote-panel.service'] = CONTROLLER_UNIT.encode()
    payload[units / 'moonlight-inner.service.d/30-graceful-stop.conf'] = GRACEFUL_DROPIN.encode()
    payload[units / 'wayvnc-campus.service.d/40-internal-panel.conf'] = CAPTURE_DROPIN.encode()
    for path in payload:
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Refusing redirected install destination: ' + str(path))
    payload = {path: data for path, data in payload.items() if not path.exists() or path.read_bytes() != data}
    for path in payload:
        print('Update:', path)
    if not apply:
        print('Check only; use --apply to install')
        return
    assert_idle(env)
    backup = home / '.local/state/remote-panel/install-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    old = {path: path.read_bytes() if path.exists() else None for path in payload}
    for path, data in old.items():
        if data is not None:
            target = backup / path.relative_to(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (backup / 'manifest.json').write_text(json.dumps({str(p.relative_to(home)): data is not None for p, data in old.items()}, indent=2))
    try:
        for path, data in payload.items():
            current = path.read_bytes() if path.exists() else None
            if current != old[path]:
                raise RuntimeError('Concurrent edit while preparing installation: ' + str(path))
            atomic_write(path, data)
        assert_idle(env)
    except BaseException:
        for path, data in old.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, data)
        raise
    subprocess.run(['systemctl', '--user', 'daemon-reload'], env=env, check=True)
    # Leave the authenticated WayVNC server and its keyboard backend running.
    subprocess.run(['systemctl', '--user', 'restart', 'remote-panel.service'], env=env, check=True)
    print('Installed. Backup:', backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    install(args.home, args.apply)
