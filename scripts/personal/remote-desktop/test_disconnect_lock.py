"""Disconnect locking regressions; isolated files and no real desktop actions."""
from pathlib import Path
import tempfile
import unittest
import remote_panel as panel

SCRATCH = None

class DisconnectLockTests(unittest.TestCase):
    def test_last_client_of_either_protocol_locks_once(self):
        self.assertTrue(hasattr(panel, 'DisconnectLock'), 'Last-client disconnect locking is missing')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            marker = Path(directory) / 'pending'
            calls = []
            lock = panel.DisconnectLock(marker, lock=lambda: calls.append('locked'))
            for vnc, moonlight in [(2, False), (1, False), (1, True), (0, True)]:
                lock.observe(vnc=vnc, moonlight=moonlight)
                lock.release()
                self.assertEqual(calls, [])
                self.assertTrue(marker.exists())
            lock.observe(vnc=0, moonlight=False)
            lock.release()
            self.assertEqual(calls, ['locked'])
            self.assertFalse(marker.exists())
            lock.release()
            self.assertEqual(calls, ['locked'])

    def test_runtime_locks_before_restoration_and_retries_failure(self):
        self.assertTrue(hasattr(panel.PanelRuntime, 'observe_remote'), 'Runtime lock integration is missing')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            root = Path(directory)
            config = root / 'config.kdl'
            config.write_text('debug {\n' + panel.ON + '}\n')
            events = []
            def lock_screen():
                events.append('lock')
                if events.count('lock') == 1:
                    raise RuntimeError('Locker unavailable')
            class Lease:
                def release(self):
                    events.append('restore')
            lock = panel.DisconnectLock(root / 'pending', lock_screen)
            runtime = panel.PanelRuntime(config, str(root / 'absent'), output_lease=Lease(),
                                         disconnect_lock=lock)
            runtime.observe_remote(vnc=1, moonlight=False)
            with self.assertRaises(RuntimeError):
                runtime.apply(False, False)
            self.assertEqual(events, [], 'Other active remote sessions must prevent locking/restoration')
            with self.assertRaisesRegex(RuntimeError, 'Locker unavailable'):
                runtime.observe_remote(vnc=0, moonlight=False)
            self.assertTrue(lock.marker.exists())
            self.assertNotIn('restore', events)
            runtime.observe_remote(vnc=0, moonlight=False)
            runtime.apply(False, False)
            self.assertEqual(events, ['lock', 'lock', 'restore'])
            self.assertIn(panel.OFF, config.read_text())

    def test_locker_requires_verified_locked_status(self):
        from desktop_backend import DesktopSession
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / '.config/desktop-profiles/inir/niri'
            root.mkdir(parents=True)
            (home / '.config/niri').symlink_to(root)
            calls = []
            statuses = iter(['unlocked', 'locked', 'secure'])
            def run(*args):
                calls.append(args)
                return next(statuses) if args[-1] == 'status' else ''
            session = DesktopSession({'XDG_CURRENT_DESKTOP': 'niri'}, home=home, invoke=run)
            session.lock(sleep=lambda _: None)
            self.assertEqual(calls[1][-3:], ('call', 'lock', 'activate'))
            self.assertEqual(sum(c[-1] == 'status' for c in calls), 3)
            session.invoke = lambda *args: 'locked' if args[-1] == 'status' else ''
            with self.assertRaisesRegex(RuntimeError, 'did not confirm'):
                session.lock(sleep=lambda _: None, timeout=0)

    def test_idle_does_not_lock_but_crash_obligation_survives_restart(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            marker = Path(directory) / 'pending'
            calls = []
            lock = panel.DisconnectLock(marker, lambda: calls.append('lock'))
            lock.observe(vnc=0, moonlight=False)
            lock.release()
            self.assertEqual(calls, [])
            lock.observe(vnc=1, moonlight=False)
            restarted = panel.DisconnectLock(marker, lambda: calls.append('lock'))
            restarted.observe(vnc=1, moonlight=False)
            restarted.release()
            self.assertEqual(calls, [])
            restarted.observe(vnc=0, moonlight=False)
            restarted.release()
            self.assertEqual(calls, ['lock'])

    def test_cleanup_refreshes_remaining_clients_before_restoration(self):
        import inspect
        import inner_moonlight as inner
        self.assertIn('refresh', inspect.signature(inner.cleanup).parameters,
                      'Moonlight cleanup must refresh surviving VNC clients')
        events = []
        class Runtime:
            def shutdown(self):
                events.append('restore')
        def refresh():
            events.append('lock-confirmed')
        inner.cleanup(Runtime(), manage=lambda action, unit: events.append(action), refresh=refresh)
        self.assertEqual(events, ['stop', 'lock-confirmed', 'restore', 'start'])
        events.clear()
        def fail_refresh():
            raise RuntimeError('Remote client remains or locking failed')
        with self.assertRaises(RuntimeError):
            inner.cleanup(Runtime(), manage=lambda action, unit: events.append(action), refresh=fail_refresh)
        self.assertEqual(events, ['stop'])

if __name__ == '__main__':
    unittest.main()
