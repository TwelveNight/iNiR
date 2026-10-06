#!/usr/bin/env python3
"""Repair skwd surfaces after Niri output hotplug settles; keep saved per-output choices."""
import json
import os
import select
import subprocess
import sys
import time

SETTLE_SECONDS = 3.0


def active_outputs(outputs):
    return {name: (out.get('current_mode'), out['logical'].get('scale'),
                   out['logical'].get('width'), out['logical'].get('height'))
            for name, out in outputs.items()
            if out.get('current_mode') is not None and out.get('logical') is not None}


def restore(names):
    # Query at execution time so a user wallpaper change during debounce wins.
    result = subprocess.run(['skwd-helm', 'outputs', '--json'], capture_output=True,
                            text=True, timeout=8, check=True)
    outputs = json.loads(result.stdout)['outputs']
    live = active_outputs(json.loads(subprocess.check_output(
        ['niri', 'msg', '-j', 'outputs'], text=True, timeout=5)))
    layers = json.loads(subprocess.check_output(
        ['niri', 'msg', '-j', 'layers'], text=True, timeout=5))
    rendered = {layer.get('output') for layer in layers
                if layer.get('namespace', '').startswith('skwd-')
                and layer.get('layer') in ('Background', 'Bottom')}
    for output in outputs:
        name = output.get('name')
        path = output.get('path') or output.get('current')
        if name not in names or name not in live or name in rendered or not output.get('connected') or not path:
            continue
        # Explicit targets force recreation; wildcard restore can mistake a live
        # process with a dropped Wayland surface for a healthy multi-output wall.
        subprocess.run(['skwd-helm', 'apply', path, '-o', name], capture_output=True,
                       text=True, timeout=25, check=True)
        print(f'skwd-output-watch: restored {name}', flush=True)


class PendingOutputs:
    def __init__(self):
        self.previous = None
        self.pending = set()
        self.deadline = None

    def update(self, outputs, now):
        current = active_outputs(outputs)
        if self.previous is not None:
            self.pending.update(name for name, value in current.items()
                                if self.previous.get(name) != value)
        self.pending.intersection_update(current)
        self.previous = current
        self.deadline = now + SETTLE_SECONDS if self.pending else None

    def take(self, now):
        if self.deadline is None or now < self.deadline:
            return set()
        ready, self.pending = self.pending, set()
        self.deadline = None
        return ready


def main():
    if not os.environ.get('NIRI_SOCKET'):
        raise SystemExit('A running Niri session is required')
    if sys.argv[1:] == ['--restore-now']:
        outputs = json.loads(subprocess.check_output(['niri', 'msg', '-j', 'outputs'], text=True))
        restore(set(active_outputs(outputs)))
        return
    pending = PendingOutputs()
    # Process lifetime belongs to this service; never stop skwd or other clients.
    stream = subprocess.Popen(['niri', 'msg', '-j', 'event-stream'], stdout=subprocess.PIPE)
    buffer = b''
    try:
        while stream.poll() is None:
            ready, _, _ = select.select([stream.stdout], [], [], 0.25)
            if ready:
                chunk = os.read(stream.stdout.fileno(), 65536)
                if not chunk:
                    break
                buffer += chunk
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    event = json.loads(line)
                    if 'OutputsChanged' in event:
                        pending.update(event['OutputsChanged']['outputs'], time.monotonic())
            targets = pending.take(time.monotonic())
            if targets:
                try:
                    restore(targets)
                except (subprocess.SubprocessError, ValueError, KeyError) as error:
                    print(f'skwd-output-watch: restore failed: {error}', file=sys.stderr, flush=True)
    finally:
        if stream.poll() is None:
            stream.terminate()
        stream.wait(timeout=5)
    raise SystemExit('Niri event stream closed')


if __name__ == '__main__':
    main()
