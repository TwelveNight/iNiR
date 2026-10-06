#!/usr/bin/python3
"""Exercise the installed GNOME daemon using only a disposable keyring/bus."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/keyring/login-keyring.py'


def isolated():
    spec = importlib.util.spec_from_file_location('keyring_client', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    control = Path(os.environ['GNOME_KEYRING_CONTROL'])
    control.mkdir(mode=0o700)
    with open(Path(os.environ['HOME']) / 'daemon.log', 'w+') as log:
        daemon = subprocess.Popen(['gnome-keyring-daemon', '--foreground', '--unlock',
            '--components=secrets', '--control-directory='+str(control)], stdin=subprocess.PIPE,
            stdout=log, stderr=log)
        daemon.stdin.write(b'fixture-only-password'); daemon.stdin.close()
        try:
            for _ in range(100):
                if daemon.poll() is not None:
                    raise AssertionError('Fixture daemon exited')
                result = subprocess.run([sys.executable, str(HELPER), '--status'], capture_output=True)
                if result.returncode == 0:
                    break
                time.sleep(.05)
            else:
                raise AssertionError('Fixture keyring did not become ready')
            client = helper.LoginKeyring()
            owner = client.owner
            assert not client.locked()
            client.call(owner, '/org/freedesktop/secrets', 'org.freedesktop.Secret.Service',
                        'Lock', '(ao)', ([client.collection],))
            client.close()
            assert subprocess.run([sys.executable, str(HELPER), '--status']).returncode == 1
            wrong = subprocess.run([sys.executable, str(HELPER), '--unlock'], input=b'wrong-fixture-password',capture_output=True)
            assert wrong.returncode == 1, wrong.returncode
            good = subprocess.run(['bash', str(ROOT/'scripts/keyring/unlock.sh')],
                env=dict(os.environ,UNLOCK_PASSWORD='fixture-only-password'),capture_output=True)
            assert good.returncode == 0, good.stderr
            assert b'fixture-only-password' not in good.stdout + good.stderr
            for _ in range(10):
                assert subprocess.run([sys.executable, str(HELPER), '--status']).returncode == 0
            client = helper.LoginKeyring()
            assert client.owner == owner
            assert not client.locked()
            client.close()
            assert daemon.poll() is None
            print('PASS: locked/unlocked, wrong/correct password, 10 repeated reads; same daemon throughout')
        finally:
            daemon.terminate()
            daemon.wait(timeout=10)


if __name__ == '__main__':
    if sys.argv[1:] == ['--isolated']:
        isolated()
    else:
        with tempfile.TemporaryDirectory(prefix='inir-keyring-test-') as tmp:
            env = dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=tmp+'/config',XDG_DATA_HOME=tmp+'/data',
                XDG_CACHE_HOME=tmp+'/cache',XDG_RUNTIME_DIR=tmp+'/runtime',
                GNOME_KEYRING_CONTROL=tmp+'/runtime/keyring')
            Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
            for name in ['DBUS_SESSION_BUS_ADDRESS','UNLOCK_PASSWORD','SSH_AUTH_SOCK']:
                env.pop(name,None)
            subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--isolated'],env=env,check=True,timeout=30)
