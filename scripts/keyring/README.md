# Login keyring lifecycle

`is_unlocked.sh` returns 0 for an unlocked login collection, 1 for a locked
collection, and 2 for an unavailable or inconsistent service. It does not read
stored secrets. Both Shells use the same helper implementation.

GNOME Keyring 50 can abort when a fresh D-Bus client reads a collection property
before registering with Secret Service. `login-keyring.py` opens a session and
reads the login alias's `Locked` property on the same connection. It pins the
unique bus owner, closes its session, and leaves the daemon running.

After screen authentication, `unlock.sh` clears the inherited password variable
before starting subprocesses and passes the password only on stdin. If needed,
the Python helper sends the existing daemon's local control UNLOCK request,
matching GNOME's PAM client protocol. The socket must belong to this UID and its
peer PID must also own Secret Service. Missing services, missing collections,
or owner mismatches fail without replacing a daemon or creating a keyring.

There is no `killall`, `--login`, `--replace`, or evaluation of daemon output.
The login collection is not deleted, re-created, or assigned a new password.
`scripts/personal/configure-keyring.py` routes both D-Bus activation names to the
same systemd service used by socket activation. The installer backs up existing
user D-Bus service overrides first. No system libraries or PAM rules are edited.

Run `python3 scripts/test-login-keyring.py` to exercise a disposable HOME, a
private D-Bus, and the installed GNOME daemon using a synthetic password. It
checks locked/unlocked state, incorrect/correct passwords, repeat queries, and
stable daemon ownership. Never run deliberately crashing probes on the real bus.

Protocol references for the installed version:
- https://github.com/GNOME/gnome-keyring/blob/50.0/daemon/control/gkd-control-client.c
- https://github.com/GNOME/gnome-keyring/blob/50.0/daemon/control/gkd-control-codes.h
- https://github.com/GNOME/gnome-keyring/blob/50.0/daemon/dbus/gkd-secret-objects.c
