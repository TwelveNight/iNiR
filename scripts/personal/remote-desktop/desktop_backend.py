"""Session-scoped compositor and locker adapters for installed desktop profiles."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import socket
import stat
import struct
import time

INNER = 'eDP-2'
ENV_KEYS = ('NIRI_SOCKET', 'HYPRLAND_INSTANCE_SIGNATURE', 'WAYLAND_DISPLAY',
            'XDG_RUNTIME_DIR', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_ID',
            'DESKTOP_PROFILE', 'XDG_CONFIG_HOME', 'NOCTALIA_CONFIG_HOME', 'NOCTALIA_STATE_HOME')


def manager_environment(base=None, data=None):
    env = dict(os.environ if base is None else base)
    if data is None:
        data = json.loads(subprocess.check_output(
            ['systemctl', '--user', 'show-environment', '--output=json'], text=True, timeout=5))
    for key in ENV_KEYS:
        env.pop(key, None)
        if data.get(key):
            env[key] = data[key]
    return env


class DesktopSession:
    def __init__(self, env, home=None, invoke=None):
        self.env = env
        self.home = Path(home or Path.home())
        self.invoke = invoke or self._invoke
        desktop = env.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
        if 'niri' in desktop:
            self.kind = 'niri'
            self.address = env.get('NIRI_SOCKET', '')
            canonical = self.home / '.config/niri'
        elif 'hyprland' in desktop:
            self.kind = 'hyprland'
            signature = env.get('HYPRLAND_INSTANCE_SIGNATURE', '')
            self.address = str(Path(env.get('XDG_RUNTIME_DIR', '/nonexistent')) / 'hypr' / signature / '.socket.sock') if signature else ''
            canonical = self.home / '.config/hypr'
        else:
            raise RuntimeError('No supported active compositor published by the user manager')
        self.config_dir = canonical.resolve()
        profiles = self.home / '.config/desktop-profiles'
        if not self.config_dir.is_relative_to(profiles):
            raise RuntimeError('Active compositor configuration is not an installed desktop profile')
        self.profile = self.config_dir.relative_to(profiles).parts[0]
        if env.get('DESKTOP_PROFILE') and env['DESKTOP_PROFILE'] != self.profile:
            raise RuntimeError('Published desktop profile does not match the active config link')
        self.identity = '|'.join((self.kind, self.profile, self.address))
        self.key = hashlib.sha256(self.identity.encode()).hexdigest()[:16]
        self.managed_config = self.config_dir / 'remote-panel__custom__.kdl' if self.kind == 'niri' else None

    @classmethod
    def published(cls, home=None):
        env = manager_environment()
        # The Hyprland publisher updates compositor IPC, but older versions do
        # not import DESKTOP_PROFILE. Do not mistake that retained value for
        # the current compositor's identity.
        env.pop('DESKTOP_PROFILE', None)
        return cls(env, home=home)

    @classmethod
    def discover(cls, probe=True):
        result = cls.published()
        if not result.address or not Path(result.address).is_socket():
            raise RuntimeError('Published compositor IPC socket is unavailable')
        with socket.socket(socket.AF_UNIX) as peer:
            peer.connect(result.address)
            pid, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise RuntimeError('Compositor IPC belongs to another user')
        process = Path('/proc') / str(pid)
        expected = 'niri' if result.kind == 'niri' else 'Hyprland'
        if (process / 'comm').read_text().strip() != expected:
            raise RuntimeError('IPC peer is not the published compositor')
        inherited = dict(item.split('=', 1) for item in os.fsdecode((process / 'environ').read_bytes()).split('\0') if '=' in item)
        for key in ('DESKTOP_PROFILE', 'XDG_CONFIG_HOME', 'XDG_SESSION_ID',
                    'NOCTALIA_CONFIG_HOME', 'NOCTALIA_STATE_HOME'):
            result.env.pop(key, None)
            if inherited.get(key):
                result.env[key] = inherited[key]
        if result.env.get('DESKTOP_PROFILE', result.profile) != result.profile:
            if not result.live_handoff(pid, process):
                raise RuntimeError('Running compositor profile does not match its config link')
            result.env['DESKTOP_PROFILE'] = result.profile
        if probe:
            result.outputs()
        return result

    def live_handoff(self, pid, process):
        """Accept only an explicit handoff bound to this exact Niri process."""
        if self.kind != 'niri' or self.profile not in ('inir', 'nyxuri'):
            return False
        marker = Path(self.env['XDG_RUNTIME_DIR']) / 'desktop-profiles/niri-handoff.json'
        try:
            info = marker.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                return False
            data = json.loads(marker.read_text())
            started = (process / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
            return data == dict(pid=pid, started=started, socket=self.address,
                                profile=self.profile, config=str(self.config_dir),
                                origin_profile=self.env.get('DESKTOP_PROFILE'))
        except (OSError, ValueError, KeyError, IndexError):
            return False

    def _invoke(self, *args):
        self.assert_current()
        return subprocess.check_output(args, env=self.env, text=True, stderr=subprocess.PIPE, timeout=8)

    def assert_current(self):
        current = DesktopSession.published(home=self.home)
        if current.identity != self.identity or not Path(self.address).is_socket():
            raise RuntimeError('Desktop session changed; refusing to modify another session')

    def outputs(self):
        if self.kind == 'niri':
            return json.loads(self.invoke('niri', 'msg', '--json', 'outputs'))
        result = {}
        for monitor in json.loads(self.invoke('hyprctl', '-j', 'monitors', 'all')):
            enabled = not monitor.get('disabled', False)
            refresh = round(monitor.get('refreshRate', 60) * 1000)
            scale = monitor.get('scale', 1)
            result[monitor['name']] = {
                'name': monitor['name'], 'make': monitor.get('make'), 'model': monitor.get('model'),
                'serial': monitor.get('serial'), 'current_mode': 0 if enabled else None,
                'modes': [{'width': monitor['width'], 'height': monitor['height'], 'refresh_rate': refresh}],
                'logical': {'x': monitor['x'], 'y': monitor['y'], 'width': round(monitor['width']/scale),
                            'height': round(monitor['height']/scale), 'scale': scale,
                            'transform': monitor.get('transform', 0)} if enabled else None,
                'hyprland': monitor,
            }
        return result

    def monitor(self, name, **values):
        # JSON strings/numbers are valid Lua literals for these fields.
        current = self.outputs().get(name)
        base = {}
        if current and current.get('current_mode') is not None:
            mode = current['modes'][current['current_mode']]
            logical = current['logical']
            base = dict(mode=f'{mode["width"]}x{mode["height"]}@{mode["refresh_rate"]/1000:.3f}',
                        scale=logical['scale'], transform=logical['transform'],
                        position=f'{logical["x"]}x{logical["y"]}', disabled=False)
        elif current:
            # Disabled Hyprland outputs do not always report a current mode.
            modes = current.get('hyprland', {}).get('availableModes', [])
            preferred = modes[0].replace('Hz', '').replace(' ', '@') if modes else 'preferred'
            base = dict(mode=preferred, scale=1, transform=0, position='0x0', disabled=False)
        fields = {'output': name, **base, **values}
        code = 'hl.monitor({' + ','.join(k + '=' + json.dumps(v) for k, v in fields.items()) + '})'
        return self.invoke('hyprctl', 'eval', code)

    def command(self, *args):
        """Accept the existing controller's normalized Niri operations on either compositor."""
        if args == ('niri', 'msg', '--json', 'outputs'):
            return json.dumps(self.outputs())
        if self.kind == 'niri' or args[0] != 'niri':
            return self.invoke(*args)
        if args == ('niri', 'msg', 'action', 'power-on-monitors'):
            return self.invoke('hyprctl', 'dispatch', 'dpms', 'on', INNER)
        if args[:3] != ('niri', 'msg', 'output'):
            raise ValueError('Unsupported compositor operation')
        name, operation, *values = args[3:]
        if operation in ('on', 'off'):
            # Enabling must not replace a saved mode/scale/position with defaults.
            return self.monitor(name, disabled=operation == 'off')
        if operation == 'position':
            if values[0] != 'set':
                raise ValueError('Remote positions must be explicit')
            coords = [v for v in values[1:] if v != '--']
            return self.monitor(name, position=f'{int(coords[0])}x{int(coords[1])}')
        if operation in ('scale', 'transform', 'mode'):
            value = float(values[0]) if operation == 'scale' else int(values[0]) if operation == 'transform' else values[0]
            return self.monitor(name, **{operation: value})
        raise ValueError('Unsupported output operation: ' + operation)

    def restore(self, name, output):
        if self.kind == 'hyprland':
            old = output.get('hyprland', {})
            if output['current_mode'] is None:
                return self.monitor(name, disabled=True)
            mode = output['modes'][output['current_mode']]
            logical = output['logical']
            values = dict(disabled=False, mode=f'{mode["width"]}x{mode["height"]}@{mode["refresh_rate"]/1000:.3f}',
                          position=f'{logical["x"]}x{logical["y"]}', scale=logical['scale'], transform=logical['transform'])
            if 'vrr' in old:
                values['vrr'] = int(old['vrr'])
            return self.monitor(name, **values)
        if output['current_mode'] is None:
            return self.command('niri', 'msg', 'output', name, 'off')
        mode = output['modes'][output['current_mode']]
        logical = output['logical']
        transform = str(logical['transform']).lower().replace('flipped', 'flipped-').rstrip('-')
        self.command('niri', 'msg', 'output', name, 'mode', f'{mode["width"]}x{mode["height"]}@{mode["refresh_rate"]/1000:.3f}')
        self.command('niri', 'msg', 'output', name, 'scale', str(logical['scale']))
        self.command('niri', 'msg', 'output', name, 'transform', transform)
        self.command('niri', 'msg', 'output', name, 'on')
        self.command('niri', 'msg', 'output', name, 'position', 'set', '--', str(logical['x']), str(logical['y']))

    def locked(self):
        if self.kind == 'hyprland':
            return json.loads(self.invoke('hyprctl', '-j', 'status')).get('locked') is True
        if self.profile == 'inir':
            return self.invoke('qs', '-p', str(self.home / '.config/quickshell/inir'),
                               'ipc', 'call', 'lock', 'status').strip() == 'secure'
        if self.profile == 'nyxuri':
            return json.loads(self.invoke('noctalia', 'msg', 'status')).get('locked') is True
        raise RuntimeError('No verified lock backend for desktop profile: ' + self.profile)

    def lock(self, timeout=8, sleep=time.sleep):
        if self.locked():
            return
        if self.kind == 'hyprland':
            self.invoke('qs', '-p', str(self.home / '.config/quickshell/ii'), 'ipc', 'call', 'lock', 'activate')
        elif self.profile == 'inir':
            self.invoke('qs', '-p', str(self.home / '.config/quickshell/inir'), 'ipc', 'call', 'lock', 'activate')
        elif self.profile == 'nyxuri':
            self.invoke('noctalia', 'msg', 'session', 'lock')
        deadline = time.monotonic() + timeout
        while not self.locked():
            if time.monotonic() >= deadline:
                raise RuntimeError('Desktop did not confirm a secure lock; keeping remote layout')
            sleep(.1)
        print('remote_lock=confirmed backend=' + self.profile, flush=True)
