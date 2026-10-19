"""Cross-desktop regressions with isolated profiles and recorded compositor replies."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop_backend import DesktopSession, manager_environment
from remote_panel import OutputLease


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def session(self, profile, invoke=None):
        compositor = 'hypr' if profile == 'hyprland-ii' else 'niri'
        target = self.home / '.config/desktop-profiles' / profile / compositor
        target.mkdir(parents=True, exist_ok=True)
        link = self.home / '.config' / compositor
        link.unlink(missing_ok=True)
        link.symlink_to(target)
        env = dict(DESKTOP_PROFILE=profile, XDG_CURRENT_DESKTOP='Hyprland' if compositor == 'hypr' else 'niri',
                   XDG_RUNTIME_DIR='/run/user/1000', NIRI_SOCKET='/run/user/1000/niri.current.sock',
                   HYPRLAND_INSTANCE_SIGNATURE='current-hypr')
        return DesktopSession(env, home=self.home, invoke=invoke)

    def test_each_profile_owns_its_config_and_snapshots(self):
        keys = []
        for profile in ['inir', 'nyxuri', 'hyprland-ii']:
            session = self.session(profile)
            keys.append(session.key)
            self.assertEqual(session.profile, profile)
            if profile == 'hyprland-ii':
                self.assertIsNone(session.managed_config)
            else:
                self.assertEqual(session.managed_config.parent, session.config_dir)
                self.assertNotIn('nyxuri-desktop', str(session.managed_config))
        self.assertEqual(len(set(keys)), 3)

    def test_json_environment_removes_other_desktop_and_preserves_literal_values(self):
        env = manager_environment(base={'NIRI_SOCKET': '/old', 'HYPRLAND_INSTANCE_SIGNATURE': 'old', 'PATH': '/bin'},
                                  data={'XDG_CURRENT_DESKTOP': 'Hyprland', 'WAYLAND_DISPLAY': 'wayland-1',
                                        'HYPRLAND_INSTANCE_SIGNATURE': 'new', 'NOCTALIA_STATE_HOME': '/state with spaces;literal'})
        self.assertNotIn('NIRI_SOCKET', env)
        self.assertEqual(env['NOCTALIA_STATE_HOME'], '/state with spaces;literal')
        self.assertEqual(env['PATH'], '/bin')

    def test_mismatched_profile_and_session_transition_are_rejected(self):
        session = self.session('inir', invoke=lambda *a: '')
        bad = dict(session.env, DESKTOP_PROFILE='nyxuri')
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            DesktopSession(bad, home=self.home)
        with patch('desktop_backend.manager_environment', return_value=dict(session.env, NIRI_SOCKET='/new.sock')):
            with self.assertRaisesRegex(RuntimeError, 'session changed'):
                session.assert_current()

    def test_stale_manager_profile_does_not_override_current_compositor_link(self):
        session = self.session('hyprland-ii', invoke=lambda *a: '')
        stale = dict(session.env, DESKTOP_PROFILE='nyxuri')
        with patch('desktop_backend.manager_environment', return_value=stale):
            current = DesktopSession.published(home=self.home)
        self.assertEqual(current.profile, 'hyprland-ii')
        self.assertNotIn('DESKTOP_PROFILE', current.env)

    def test_hyprland_commands_keep_mode_scaling_and_use_lua_api(self):
        monitor = dict(name='eDP-2', width=2560, height=1600, refreshRate=165.004,
                       x=5402, y=160, scale=1.5, transform=0, disabled=False)
        calls = []
        def invoke(*args):
            calls.append(args)
            return json.dumps([monitor]) if args == ('hyprctl', '-j', 'monitors', 'all') else ''
        session = self.session('hyprland-ii', invoke)
        session.command('niri', 'msg', 'output', 'eDP-2', 'position', 'set', '--', '0', '0')
        lua = calls[-1][-1]
        self.assertEqual(calls[-1][:2], ('hyprctl', 'eval'))
        self.assertIn('position="0x0"', lua)
        self.assertIn('mode="2560x1600@165.004"', lua)
        self.assertIn('scale=1.5', lua)
        self.assertTrue(all(call[0] == 'hyprctl' for call in calls))
        session.command('niri', 'msg', 'action', 'power-on-monitors')
        self.assertEqual(calls[-1], ('hyprctl', 'dispatch', 'dpms', 'on', 'eDP-2'))

    def test_lock_routes_to_active_shell_and_confirms_compositor(self):
        for profile in ['inir', 'nyxuri', 'hyprland-ii']:
            calls = []
            states = iter([False, True])
            def invoke(*args):
                calls.append(args)
                if args[-1] == 'status':
                    locked = next(states)
                    return ('secure' if locked else 'unlocked') if profile == 'inir' else json.dumps({'locked': locked})
                return ''
            session = self.session(profile, invoke)
            session.lock(sleep=lambda _: None)
            if profile == 'nyxuri':
                self.assertIn(('noctalia', 'msg', 'session', 'lock'), calls)
            else:
                expected = 'ii' if profile == 'hyprland-ii' else 'inir'
                self.assertTrue(any(str(self.home / '.config/quickshell' / expected) in call for call in calls))
            if profile == 'hyprland-ii':
                self.assertEqual(calls[-1], ('hyprctl', '-j', 'status'))

    def test_lease_restores_internal_and_external_and_rejects_another_session(self):
        initial = {
            'eDP-2': dict(make='BOE', model='Panel', serial=None, current_mode=0,
                          modes=[dict(width=2560, height=1600, refresh_rate=165004)],
                          logical=dict(x=2560, y=80, scale=1.5, transform='Normal')),
            'HDMI-A-1': dict(make='Other', model='Monitor', serial='1', current_mode=0,
                             modes=[dict(width=2560, height=1440, refresh_rate=143995)],
                             logical=dict(x=0, y=0, scale=1, transform='Normal')),
        }
        session = self.session('inir', invoke=lambda *a: '')
        session.assert_current = lambda: None
        current = copy.deepcopy(initial)
        restored = []
        session.restore = lambda name, output: restored.append((name, output))
        def run(*args):
            if args[-1] == 'outputs':
                return json.dumps(current)
            if args[-1] == 'off':
                current[args[3]]['current_mode'] = None
        path = self.home / 'lease.json'
        lease = OutputLease(path, run=run, session=session)
        lease.acquire()
        current['eDP-2']['logical']['x'] = 0
        lease.release()
        self.assertEqual([name for name, _ in restored], ['HDMI-A-1', 'eDP-2'])
        self.assertEqual(dict(restored), initial)
        lease.remember()
        session.identity = 'another-login'
        restored.clear()
        with self.assertRaisesRegex(RuntimeError, 'another desktop session'):
            lease.release()
        self.assertEqual(restored, [])
        self.assertTrue(path.exists())


if __name__ == '__main__':
    unittest.main()
