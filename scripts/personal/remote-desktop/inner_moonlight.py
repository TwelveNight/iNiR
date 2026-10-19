"""Explicit preparation for stock Sunshine, AMD and closed-lid inner capture.
Never restore a former external-capture configuration or restart Sunshine idle.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

import remote_panel as panel

HOME = Path.home()
UNIT = 'app-dev.lizardbyte.app.Sunshine.service'
CONTROLLER = 'remote-panel.service'
CONFIG = HOME / '.config/sunshine/sunshine.conf'
SOCKET = str(Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000')) / 'wayvnc-campus.sock')
STATUS = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000')) / 'moonlight-inner.json'
ROOT = HOME / '.local/state/remote-panel/moonlight-inner'


def validate_config(text):
    expected = {'capture': 'kms', 'encoder': 'vaapi',
                'adapter_name': '/dev/dri/renderD128', 'output_name': 'eDP-2'}
    for key, value in expected.items():
        found = [line.split('=', 1)[1].strip() for line in text.splitlines()
                 if '=' in line and line.split('=', 1)[0].strip() == key]
        if found != [value]:
            raise ValueError('Refusing non-inner or ambiguous Sunshine config: ' + key)


def inner_only_ready(outputs):
    inner = outputs.get('eDP-2', {})
    logical = inner.get('logical') or {}
    return (inner.get('current_mode') is not None and
            logical.get('x') == 0 and logical.get('y') == 0 and
            all(value.get('current_mode') is None and value.get('logical') is None
                for name, value in outputs.items() if name != 'eDP-2'))


def inner_powered(drm_root=Path('/sys/class/drm')):
    connectors = list(drm_root.glob('card*-eDP-2'))
    return (len(connectors) == 1 and
            (connectors[0] / 'enabled').read_text().strip() == 'enabled' and
            (connectors[0] / 'dpms').read_text().strip() == 'On')


def ensure_inner_powered(outputs=None, run=panel.command,
                         drm_root=Path('/sys/class/drm'), timeout=8):
    outputs = outputs or outputs_now
    if not inner_only_ready(outputs()):
        raise RuntimeError('Refusing display wake outside inner-only layout')
    run('niri', 'msg', 'action', 'power-on-monitors')
    deadline = time.monotonic() + timeout
    while not inner_powered(drm_root):
        if time.monotonic() >= deadline or not inner_only_ready(outputs()):
            raise RuntimeError('Internal panel did not become powered; refusing capture')
        time.sleep(.1)


def capture_probe_ready(log):
    return ('Screencasting with KMS' in log and
            'Found H.264 encoder: h264_vaapi [vaapi]' in log and
            'Starting main loop' in log and
            'Fatal:' not in log and 'Unable to initialize capture method' not in log)


def manager_is_preparing(status, service_pid):
    return (service_pid > 0 and status.get('manager_pid') == service_pid and
            status.get('state') in ('starting-capture', 'ready', 'streaming'))


def outputs_now():
    return panel.DesktopSession.discover().outputs()


def systemctl(action, unit):
    subprocess.run(['systemctl', '--user', action, unit], check=True, timeout=35)


def cleanup(runtime, manage=systemctl, refresh=None):
    # Fail closed: never turn on an external screen if capture could still run.
    manage('stop', UNIT)
    if refresh is not None:
        refresh()
    runtime.shutdown()
    manage('start', CONTROLLER)


class SessionPolicy:
    def __init__(self, now, timeout):
        self.deadline = now + timeout
        self.last_active = None

    def hold(self, now, moonlight, vnc):
        if moonlight or vnc:
            self.last_active = now
            return True
        if self.last_active is None:
            return now < self.deadline
        return now - self.last_active < 2


def set_status(**fields):
    fields['updated_at'] = time.time()
    fields['manager_pid'] = os.getpid()
    tmp = STATUS.with_suffix('.new')
    if STATUS.exists() and 'session' not in fields:
        previous = json.loads(STATUS.read_text())
        if previous.get('manager_pid') == os.getpid() and 'session' in previous:
            fields['session'] = previous['session']
    tmp.write_text(json.dumps(fields) + '\n')
    tmp.replace(STATUS)
    print(json.dumps(fields), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guard', action='store_true')
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    validate_config(CONFIG.read_text())
    if args.guard:
        status = json.loads(STATUS.read_text()) if STATUS.exists() else {}
        service_pid = int(subprocess.check_output(['systemctl', '--user', 'show', 'moonlight-inner.service', '-p', 'MainPID', '--value'], text=True).strip() or '0')
        session = panel.DesktopSession.discover()
        ready = (manager_is_preparing(status, service_pid) and status.get('session') == session.identity
                 and inner_only_ready(session.outputs()))
        print('inner-only capture gate: ' + ('ready' if ready else 'not prepared; Sunshine skipped'))
        return 0 if ready else 1
    if args.timeout <= 0:
        raise ValueError('Preparation timeout must be positive')
    if panel.rpc(SOCKET, 'client-list') or panel.sunshine_active(UNIT, CONFIG):
        raise RuntimeError('A real remote session is active; refusing to interrupt it')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    session = panel.DesktopSession.discover()
    runtime = panel.PanelRuntime(session.managed_config, SOCKET, run=session.command,
                                output_lease=panel.OutputLease(ROOT / (session.key + '-outputs.json'),
                                                              run=session.command, session=session),
                                disconnect_lock=panel.disconnect_lock(session), session=session)
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    touched = False
    outcome = 'failed'
    try:
        touched = True
        systemctl('stop', UNIT)
        systemctl('stop', CONTROLLER)
        runtime.apply(True, False)
        session.command('niri', 'msg', 'output', 'eDP-2', 'position', 'set', '0', '0')
        deadline = time.monotonic() + 8
        while not inner_only_ready(session.outputs()):
            if time.monotonic() > deadline or stopping:
                raise RuntimeError('Internal-only layout not ready; refusing capture')
            time.sleep(.1)
        ensure_inner_powered(outputs=session.outputs, run=session.command)
        set_status(state='starting-capture', capture='eDP-2', session=session.identity)
        systemctl('start', UNIT)
        invocation = subprocess.check_output(
            ['systemctl', '--user', 'show', UNIT, '-p', 'InvocationID', '--value'],
            text=True, timeout=5).strip()
        if not invocation:
            raise RuntimeError('Sunshine did not start a live invocation')
        deadline = time.monotonic() + 35
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:47989/serverinfo', timeout=1) as response:
                    log = subprocess.check_output(
                        ['journalctl', '--user', '-b', '_SYSTEMD_INVOCATION_ID=' + invocation,
                         '--no-pager', '-o', 'cat'], text=True, timeout=5)
                    if response.status == 200 and inner_powered() and capture_probe_ready(log):
                        break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() > deadline or stopping:
                raise RuntimeError('Sunshine capture/encoder not ready; HTTP alone is insufficient')
            time.sleep(.25)
        policy = SessionPolicy(time.monotonic(), args.timeout)
        outcome = 'ready'
        set_status(state=outcome, encoder='vaapi', capture='eDP-2', external_off=True,
                   preparation_expires_at=time.time() + args.timeout)
        last_vnc = False
        while not stopping:
            if not inner_only_ready(session.outputs()):
                raise RuntimeError('Capture layout changed; stopping rather than capturing an external screen')
            vnc = len(panel.rpc(SOCKET, 'client-list'))
            moonlight = panel.sunshine_active(UNIT, CONFIG)
            try:
                runtime.observe_remote(vnc=vnc, moonlight=moonlight)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                set_status(state='lock-pending', error=str(error), capture='eDP-2')
                time.sleep(.5)
                continue  # Keep the inner-only layout and retry the lock, never expose the external.
            if not policy.hold(time.monotonic(), moonlight, vnc):
                outcome = 'disconnected' if policy.last_active is not None else 'preparation-expired'
                break
            if bool(vnc) != last_vnc:
                runtime.apply(True, bool(vnc))
                last_vnc = bool(vnc)
            if moonlight and outcome != 'streaming':
                outcome = 'streaming'
                set_status(state=outcome, encoder='vaapi', capture='eDP-2', external_off=True)
            time.sleep(.25)
        if stopping:
            outcome = 'stopped'
    finally:
        if touched:
            try:
                set_status(state='restoring', outcome=outcome)
                cleanup(runtime, refresh=lambda: runtime.observe_remote(
                    vnc=len(panel.rpc(SOCKET, 'client-list')), moonlight=False))
            except Exception as error:
                set_status(state='cleanup-failed', outcome=outcome, error=str(error))
                raise
        set_status(state='idle', outcome=outcome, sunshine='stopped', capture='eDP-2')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
