"""Wait for the actual Niri internal output before starting stock Sunshine."""
import json
import subprocess
import time


def read_niri_outputs():
    from desktop_backend import DesktopSession
    return DesktopSession.discover().outputs()


def wait_ready(timeout=15, *, read_outputs=read_niri_outputs, sleep=time.sleep, clock=time.monotonic):
    deadline = clock() + timeout
    while True:
        try:
            panel = read_outputs().get('eDP-2', {})
            if panel.get('current_mode') is not None and panel.get('logical') is not None:
                return True
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        if clock() >= deadline:
            raise RuntimeError('eDP-2 is not ready; refusing to start Sunshine on another output')
        sleep(.1)


if __name__ == '__main__':
    wait_ready()
    print('Verified internal output eDP-2 ready for Sunshine', flush=True)
