"""Manage remote output leases, optionally keeping the laptop panel ready."""

from pathlib import Path
import argparse
import json
import os
import select
import signal
import socket
import subprocess
import tempfile
import time

from desktop_backend import DesktopSession, manager_environment

MANAGED_CONFIG = Path.home() / '.config/niri/remote-panel__custom__.kdl'


def desktop_environment(manager_text=None, base=None):
    # Use systemd's JSON representation: text shell-escapes semicolons/spaces.
    data = json.loads(manager_text) if manager_text is not None else None
    return manager_environment(base=base, data=data)


def command(*args):
    return subprocess.check_output(args, env=desktop_environment(), text=True,
                                   stderr=subprocess.PIPE, timeout=8)


def rpc(path, method, params=None):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(3)
        sock.connect(str(path))
        request = {'method': method, 'id': 1}
        if params is not None:
            request['params'] = params
        sock.sendall(json.dumps(request).encode())
        data = ''
        while len(data) < 1048576:
            chunk = sock.recv(65536)
            if not chunk:
                raise ConnectionError('WayVNC control connection closed')
            data += chunk.decode()
            try:
                result = json.loads(data)
            except json.JSONDecodeError:
                continue
            if result.get('code') != 0:
                raise RuntimeError(f'WayVNC {method}: {result}')
            return result.get('data')
        raise RuntimeError('WayVNC response too large')


def lock_screen():
    DesktopSession.discover().lock()


def disconnect_lock(session=None):
    suffix = '-' + session.key if session else ''
    return DisconnectLock(Path(os.environ['XDG_RUNTIME_DIR']) / ('remote-panel' + suffix + '.lock-required'),
                          lock=session.lock if session else lock_screen)


class DisconnectLock:
    """Persist a lock obligation across controller restarts until lock succeeds."""
    def __init__(self, marker, lock):
        self.marker = Path(marker)
        self.lock = lock
        self.active = False

    def observe(self, *, vnc, moonlight):
        self.active = bool(vnc or moonlight)
        if self.active and not self.marker.exists():
            self.marker.write_text('Remote desktop session observed; lock before restoring displays.\n')
            self.marker.chmod(0o600)

    def release(self):
        if not self.active and self.marker.exists():
            self.lock()
            self.marker.unlink()


class OutputLease:
    """Persist the pre-remote external output layout until the final disconnect."""
    def __init__(self, path, run=command, session=None):
        self.path = Path(path)
        self.run = run
        self.session = session

    def remember(self):
        if self.path.exists():
            return
        outputs = json.loads(self.run('niri', 'msg', '--json', 'outputs'))
        external = ({'session': self.session.identity, 'outputs': outputs} if self.session else
                    {name: data for name, data in outputs.items() if name != 'eDP-2'})
        temp = self.path.with_suffix(self.path.suffix + '.new')
        temp.write_text(json.dumps(external))
        temp.chmod(0o600)
        temp.replace(self.path)

    def acquire(self):
        self.remember()
        outputs = json.loads(self.run('niri', 'msg', '--json', 'outputs'))
        for name, output in outputs.items():
            if name != 'eDP-2' and output.get('current_mode') is not None:
                self.run('niri', 'msg', 'output', name, 'off')

    def release(self):
        if not self.path.exists():
            return
        snapshot = json.loads(self.path.read_text())
        if self.session:
            self.session.assert_current()
            if snapshot.get('session') != self.session.identity:
                raise RuntimeError('Display snapshot belongs to another desktop session')
            snapshot = snapshot['outputs']
        # Restore external displays before the panel, which may originally be off.
        snapshot = dict(sorted(snapshot.items(), key=lambda item: item[0] == 'eDP-2'))
        outputs = json.loads(self.run('niri', 'msg', '--json', 'outputs'))
        for name, output in snapshot.items():
            current = outputs.get(name)
            if current is None:
                continue  # Disconnected hardware must not be forced on.
            if any(current.get(k) != output.get(k) for k in ('make', 'model', 'serial')):
                continue  # Do not apply another monitor's saved layout.
            if self.session:
                self.session.restore(name, output)
                continue
            if output.get('current_mode') is None:
                self.run('niri', 'msg', 'output', name, 'off')
                continue
            mode = output['modes'][output['current_mode']]
            refresh = mode['refresh_rate'] / 1000
            self.run('niri', 'msg', 'output', name, 'mode', f'{mode["width"]}x{mode["height"]}@{refresh:.3f}')
            logical = output['logical']
            self.run('niri', 'msg', 'output', name, 'scale', str(logical['scale']))
            transform = str(logical['transform']).lower().replace('flipped', 'flipped-').rstrip('-')
            self.run('niri', 'msg', 'output', name, 'transform', transform)
            self.run('niri', 'msg', 'output', name, 'on')
            self.run('niri', 'msg', 'output', name, 'position', 'set', '--', str(logical['x']), str(logical['y']))
        self.path.unlink()


class PanelRuntime:
    def __init__(self, config, control_socket, run=command, output_lease=None, keep_ready=False,
                 disconnect_lock=None, session=None):
        self.config = Path(config) if config is not None else None
        self.session = session
        self.lid_inhibitor = None
        self.control_socket = control_socket
        self.run = run
        self.output_lease = output_lease
        self.keep_ready = keep_ready
        self.disconnect_lock = disconnect_lock

    def observe_remote(self, *, vnc, moonlight):
        if self.disconnect_lock is not None:
            self.disconnect_lock.observe(vnc=vnc, moonlight=moonlight)
            self.disconnect_lock.release()

    def set_override(self, active):
        if self.session:
            self.session.assert_current()
            if active and self.lid_inhibitor is None:
                self.lid_inhibitor = subprocess.Popen(
                    ['systemd-inhibit', '--what=handle-lid-switch', '--mode=block',
                     '--who=Remote desktop', '--why=Remote internal screen capture', 'sleep', 'infinity'],
                    env=self.session.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif not active and self.lid_inhibitor is not None:
                self.lid_inhibitor.terminate()
                self.lid_inhibitor.wait(timeout=3)
                self.lid_inhibitor = None
        if self.config is None:
            return  # Hyprland has no Niri lid debug flag.
        old = self.config.read_text()
        new = render_override(old, active)
        if new == old:
            return
        # Atomic replacement avoids Niri observing a truncated/half-written config.
        fd, name = tempfile.mkstemp(prefix='.remote-panel-', suffix='.kdl', dir=self.config.parent)
        try:
            with os.fdopen(fd, 'w') as file:
                file.write(new)
            os.chmod(name, self.config.stat().st_mode & 0o777)
            if self.config.read_text() != old:
                raise RuntimeError('Config changed concurrently; retrying without overwriting')
            os.replace(name, self.config)
        finally:
            Path(name).unlink(missing_ok=True)

    def detach(self):
        if not Path(self.control_socket).exists():
            return
        try:
            if rpc(self.control_socket, 'output-list'):
                rpc(self.control_socket, 'detach')
        except (FileNotFoundError, ConnectionRefusedError):
            pass

    def apply(self, active, vnc):
        if self.session:
            self.session.assert_current()
        if not active and self.disconnect_lock is not None:
            if self.disconnect_lock.active:
                raise RuntimeError('Refusing display restoration while a remote client remains')
            self.disconnect_lock.release()
        if not vnc:
            self.detach()
        if self.output_lease:
            if active:
                self.output_lease.remember()
            else:
                # Restore external first: a closed lid must not leave zero outputs.
                self.output_lease.release()
        panel_enabled = active or self.keep_ready
        self.set_override(panel_enabled)
        if panel_enabled:
            self.run('niri', 'msg', 'output', 'eDP-2', 'on')
            deadline = time.monotonic() + 5
            while True:
                outputs = json.loads(self.run('niri', 'msg', '--json', 'outputs'))
                if outputs.get('eDP-2', {}).get('current_mode') is not None:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Niri did not enable eDP-2')
                time.sleep(.1)
            self.run('niri', 'msg', 'output', 'eDP-2', 'position', 'set', '0', '0')
            if vnc:
                outputs = rpc(self.control_socket, 'output-list')
                if not any(o['name'] == 'eDP-2' and o['captured'] for o in outputs):
                    if outputs:
                        rpc(self.control_socket, 'output-set', {'output-name': 'eDP-2'})
                    else:
                        rpc(self.control_socket, 'attach', {'display': desktop_environment()['WAYLAND_DISPLAY'], 'output': 'eDP-2'})
        if active and self.output_lease:
            self.output_lease.acquire()
        if vnc:
            # Output on/current_mode does not undo lock-screen DPMS blanking.
            # Wake only after the external lease has disabled other outputs.
            self.run('niri', 'msg', 'action', 'power-on-monitors')
        print(f'panel_override={panel_enabled} remote_active={active} wayvnc_capture={vnc}', flush=True)

    def shutdown(self):
        self.keep_ready = False
        try:
            self.apply(False, False)
        finally:
            if self.lid_inhibitor is not None:
                self.lid_inhibitor.terminate()
                self.lid_inhibitor.wait(timeout=3)
                self.lid_inhibitor = None


class ActiveRuntime:
    """Resolve the currently published session; never restore another login's lease."""
    def __init__(self, control_socket, status, keep_ready=False, config=None):
        self.control_socket = control_socket
        self.status = status
        self.keep_ready = keep_ready
        self.config = config
        self.runtime = None
        self.last_discovery = 0

    def current(self):
        if self.runtime is not None and time.monotonic() - self.last_discovery < .5:
            return self.runtime
        published = DesktopSession.published()
        self.last_discovery = time.monotonic()
        if self.runtime is not None and self.runtime.session.identity == published.identity:
            self.runtime.session.assert_current()
            return self.runtime
        session = DesktopSession.discover()
        if self.runtime is None or self.runtime.session.identity != session.identity:
            if self.runtime is not None and self.runtime.lid_inhibitor is not None:
                self.runtime.lid_inhibitor.terminate()
                self.runtime.lid_inhibitor.wait(timeout=3)
            lease = OutputLease(self.status + '.' + session.key + '.outputs.json',
                                run=session.command, session=session)
            self.runtime = PanelRuntime(self.config or session.managed_config, self.control_socket,
                                        run=session.command, output_lease=lease, keep_ready=self.keep_ready,
                                        disconnect_lock=disconnect_lock(session), session=session)
        return self.runtime

    def observe_remote(self, **clients):
        self.current().observe_remote(**clients)

    def apply(self, active, vnc):
        self.current().apply(active, vnc)

    @property
    def disconnect_lock(self):
        return self.current().disconnect_lock

    def shutdown(self):
        if self.runtime is not None:
            self.runtime.shutdown()


def owned_udp_ports(pid):
    """Return UDP ports whose socket inode belongs to this exact process."""
    root = Path('/proc') / str(pid)
    try:
        inodes = set()
        for fd in (root / 'fd').iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith('socket:['):
                    inodes.add(target[8:-1])
            except FileNotFoundError:
                continue
        ports = set()
        for table in ('udp', 'udp6'):
            for line in (root / 'net' / table).read_text().splitlines()[1:]:
                fields = line.split()
                if fields[9] in inodes:
                    ports.add(int(fields[1].rsplit(':', 1)[1], 16))
        return ports
    except (FileNotFoundError, ProcessLookupError):
        return set()


def stream_ports_active(ports, base):
    # Video/audio shared sockets live until the last stream worker releases them.
    return {base + 9, base + 11}.issubset(ports)


def cgroup_udp_ports(text, group):
    """Use kernel socket cgroup metadata, even for non-dumpable Sunshine."""
    if not group:
        return set()
    ports = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 6 or 'cgroup:' + group not in fields[5:]:
            continue
        try:
            ports.add(int(fields[3].rsplit(':', 1)[1]))
        except (ValueError, IndexError):
            continue
    return ports


def sunshine_active(unit, config):
    props = dict(line.split('=', 1) for line in command(
        'systemctl', '--user', 'show', unit,
        '--property=MainPID,ControlGroup,ActiveState').splitlines() if '=' in line)
    if int(props.get('MainPID') or '0') <= 0 or props.get('ActiveState') != 'active':
        return False
    group = props.get('ControlGroup', '')
    if not group:
        return False
    base = 47989
    for line in Path(config).read_text().splitlines():
        if '=' in line and line.split('=', 1)[0].strip() == 'port':
            base = int(line.split('=', 1)[1].strip())
    ports = cgroup_udp_ports(command('ss', '-H', '-uan', '--cgroup'), group)
    return stream_ports_active(ports, base)


OFF = '    // remote-panel-managed: keep-laptop-panel-on-when-lid-is-closed\n'
ON = '    keep-laptop-panel-on-when-lid-is-closed // remote-panel-managed\n'


def render_override(text, active):
    """Touch exactly the marked line, refusing missing or duplicate ownership."""
    if text.count(OFF) + text.count(ON) != 1:
        raise ValueError('Expected exactly one remote-panel-managed marker')
    old = ON if ON in text else OFF
    return text.replace(old, ON if active else OFF, 1)


class ConnectionPolicy:
    """Keep either protocol alive until its own last client leaves."""
    def __init__(self, apply):
        self.apply = apply
        self.state = None

    def update(self, *, vnc, moonlight):
        # Explicit Moonlight preparation owns its own display lease. Geometry must stay
        # stable after capture/input initialization; never move it mid-stream.
        desired = (vnc > 0, vnc > 0)
        if desired != self.state:
            self.apply(*desired)
            self.state = desired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='Override the active profile lid-policy file')
    parser.add_argument('--vnc-socket', default=os.environ['XDG_RUNTIME_DIR']+'/wayvnc-campus.sock')
    parser.add_argument('--status', default=os.environ['XDG_RUNTIME_DIR']+'/remote-panel.json')
    parser.add_argument('--sunshine-unit', default='app-dev.lizardbyte.app.Sunshine.service')
    parser.add_argument('--sunshine-config', default=str(Path.home()/'.config/sunshine/sunshine.conf'))
    parser.add_argument('--keep-panel-ready', action='store_true',
                        help='Keep the internal output available before Moonlight connects')
    args = parser.parse_args()
    runtime = ActiveRuntime(args.vnc_socket, args.status, args.keep_panel_ready, args.config)
    policy = ConnectionPolicy(runtime.apply)
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # wayvncctl reconnects and gives a startup event on every successful resubscribe.
    events = subprocess.Popen(['wayvncctl', '-S', args.vnc_socket, '-j', '-w', '-r', 'event-receive'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    fd = events.stdout.fileno()
    os.set_blocking(fd, False)
    pending = b''
    count = None  # Unknown is not a disconnect; reconcile with the real server first.
    moonlight = False
    last_seen = None
    next_sunshine = 0
    last_status = None
    last_error = None
    try:
        while running:
            now = time.monotonic()
            if events.poll() is not None:
                raise RuntimeError('WayVNC event monitor exited')
            readable, _, _ = select.select([fd], [], [], .25)
            if readable:
                pending += os.read(fd, 65536)
                while b'\n' in pending:
                    raw, pending = pending.split(b'\n', 1)
                    event = json.loads(raw)
                    kind = event.get('method')
                    if kind == 'wayvnc-startup':
                        count = len(rpc(args.vnc_socket, 'client-list'))
                        policy.state = None
                    elif kind == 'wayvnc-shutdown':
                        count = 0
                    elif kind in ('client-connected', 'client-disconnected'):
                        count = int(event['params']['connection_count'])
                    elif kind in ('detached', 'capture-changed') and count:
                        policy.state = None
            try:
                if count is None:
                    count = len(rpc(args.vnc_socket, 'client-list'))
                if now >= next_sunshine:
                    moonlight = sunshine_active(args.sunshine_unit, args.sunshine_config)
                    next_sunshine = now + 1
                # Observe both protocols before any display/lid restoration.
                runtime.observe_remote(vnc=count, moonlight=moonlight)
                identity = runtime.current().session.identity
                if getattr(policy, 'session', None) != identity:
                    policy.state = None
                    policy.session = identity
                if count or moonlight:
                    last_seen = now
                # Small disconnect grace prevents flicker during reconnects.
                held = not (count or moonlight) and last_seen is not None and now-last_seen < 2
                policy.update(vnc=count, moonlight=moonlight or held)
                active, capturing = policy.state or (False, False)
                status = {'wayvnc_clients': count, 'moonlight_stream': moonlight,
                          'disconnect_grace': held,
                          'panel_override': active or args.keep_panel_ready,
                          'remote_active': active,
                          'keep_panel_ready': args.keep_panel_ready,
                          'wayvnc_capture': capturing,
                          'disconnect_lock_enabled': True,
                          'lock_required': runtime.disconnect_lock.marker.exists(),
                          'desktop_profile': runtime.current().session.profile}
                if status != last_status:
                    temporary = Path(args.status + '.new')
                    temporary.write_text(json.dumps(status) + '\n')
                    temporary.replace(args.status)
                    print(json.dumps(status), flush=True)
                    last_status = status
                last_error = None
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                text = str(error)
                if text != last_error:
                    print('retrying: ' + text, flush=True)
                    last_error = text
                time.sleep(.5)
    finally:
        events.terminate()
        try:
            events.wait(timeout=3)
        except subprocess.TimeoutExpired:
            events.kill()
            events.wait()
        # Deliberately stopped controller restores the original Niri lid policy.
        runtime.shutdown()


if __name__ == '__main__':
    main()
