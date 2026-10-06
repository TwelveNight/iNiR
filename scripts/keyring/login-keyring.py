#!/usr/bin/python3
"""Query/unlock the existing login keyring without replacing its daemon.

GNOME Keyring 50 needs an established client before Collection properties are
read. The control UNLOCK message below is the same protocol used by its PAM
module (daemon/control/gkd-control-client.c); it neither creates nor deletes keys.
Exit codes: 0 unlocked, 1 locked/denied, 2 unavailable or inconsistent service.
"""
import os
from pathlib import Path
import socket
import stat
import struct
import sys

from gi.repository import Gio, GLib


class LoginKeyring:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.owner = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                               'org.freedesktop.DBus', 'GetNameOwner',
                               '(s)', ('org.freedesktop.secrets',))[0]
        # Use one connection and pin its destination throughout the operation.
        _, self.session = self.call(self.owner, '/org/freedesktop/secrets',
            'org.freedesktop.Secret.Service', 'OpenSession',
            '(sv)', ('plain', GLib.Variant('s', '')))
        self.collection = self.call(self.owner, '/org/freedesktop/secrets',
            'org.freedesktop.Secret.Service', 'ReadAlias', '(s)', ('login',))[0]
        if self.collection == '/':
            raise RuntimeError('No login collection')

    def call(self, dest, path, interface, method, signature=None, args=()):
        return self.bus.call_sync(dest, path, interface, method,
            GLib.Variant(signature, args) if signature else None, None,
            Gio.DBusCallFlags.NO_AUTO_START, 5000, None).unpack()

    def locked(self):
        return self.call(self.owner, self.collection, 'org.freedesktop.DBus.Properties',
                         'Get', '(ss)', ('org.freedesktop.Secret.Collection', 'Locked'))[0]

    def close(self):
        self.call(self.owner, self.session, 'org.freedesktop.Secret.Session', 'Close')

    def unlock(self, password):
        directory = os.environ.get('GNOME_KEYRING_CONTROL') or str(Path(os.environ['XDG_RUNTIME_DIR']) / 'keyring')
        path = Path(directory) / 'control'
        info = path.lstat()
        if info.st_uid != os.getuid() or not stat.S_ISSOCK(info.st_mode):
            raise RuntimeError('Invalid control socket')
        expected_pid = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'GetConnectionUnixProcessID', '(s)', (self.owner,))[0]
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(5)
            peer.connect(str(path))
            pid, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid() or pid != expected_pid:
                raise RuntimeError('Control socket and Secret Service have different owners')
            # NUL credential handshake, then length/opcode/string-length/string.
            packet = bytearray(struct.pack('!III', 12 + len(password), 1, len(password)))
            packet.extend(password)
            try:
                peer.sendall(b'\0')
                peer.sendall(packet)
            finally:
                packet[:] = b'\0' * len(packet)
            reply = bytearray()
            while len(reply) < 8:
                chunk = peer.recv(8 - len(reply))
                if not chunk:
                    raise RuntimeError('Incomplete control reply')
                reply.extend(chunk)
            length, result = struct.unpack('!II', reply)
            if length != 8 or result not in (0, 1, 2, 3):
                raise RuntimeError('Invalid control reply')
            return result == 0 and not self.locked()


def main():
    password = bytearray()
    client = None
    try:
        if sys.argv[1:] not in (['--status'], ['--unlock']):
            return 2
        if sys.argv[1] == '--unlock':
            password = bytearray(sys.stdin.buffer.read(8193))
            if not password or len(password) > 8192 or b'\0' in password:
                return 2
        client = LoginKeyring()
        if not client.locked():
            return 0
        if sys.argv[1] == '--status':
            return 1
        return 0 if client.unlock(password) else 1
    except (GLib.Error, OSError, RuntimeError, KeyError):
        print('Login keyring unavailable; its daemon was not replaced.', file=sys.stderr)
        return 2
    finally:
        password[:] = b'\0' * len(password)
        if client:
            try:
                client.close()
            except GLib.Error:
                pass


if __name__ == '__main__':
    sys.exit(main())
