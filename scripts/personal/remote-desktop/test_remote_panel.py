"""Connection-scoped laptop-panel policy regression tests."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name('remote_panel.py')

class PolicyTests(unittest.TestCase):
    def test_last_remote_disconnect_restores_policy(self):
        self.assertTrue(MODULE.is_file(), 'Connection-scoped panel controller is not implemented')
        spec = importlib.util.spec_from_file_location('remote_panel', MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        calls = []
        policy = mod.ConnectionPolicy(lambda *args: calls.append(args))
        policy.update(vnc=1, moonlight=0)
        policy.update(vnc=1, moonlight=1)
        policy.update(vnc=0, moonlight=1)
        policy.update(vnc=0, moonlight=0)
        self.assertEqual(calls, [(True, True), (False, False)])

    def test_failed_apply_is_retried(self):
        import remote_panel as mod
        calls = []
        def apply(active, vnc):
            calls.append((active, vnc))
            if len(calls) == 1:
                raise RuntimeError('temporary compositor delay')
        policy = mod.ConnectionPolicy(apply)
        with self.assertRaises(RuntimeError):
            policy.update(vnc=1, moonlight=0)
        policy.update(vnc=1, moonlight=0)
        self.assertEqual(calls, [(True, True), (True, True)])

class DesktopEnvironmentTests(unittest.TestCase):
    def test_current_manager_compositor_values_replace_missing_or_stale_boot_environment(self):
        import remote_panel as mod
        env = mod.desktop_environment(
            '{"NIRI_SOCKET":"/run/user/1000/niri.current.sock","WAYLAND_DISPLAY":"wayland-1",'
            '"XDG_RUNTIME_DIR":"/run/user/1000","UNRELATED":"must-not-import"}',
            {'NIRI_SOCKET': '/old/socket', 'PATH': '/usr/bin'})
        self.assertEqual(env['NIRI_SOCKET'], '/run/user/1000/niri.current.sock')
        self.assertEqual(env['WAYLAND_DISPLAY'], 'wayland-1')
        self.assertEqual(env['PATH'], '/usr/bin')
        self.assertNotIn('UNRELATED', env)

class ConfigTests(unittest.TestCase):
    def test_default_managed_config_survives_upstream_main_config_replacement(self):
        import remote_panel as mod
        self.assertEqual(mod.MANAGED_CONFIG.name, 'remote-panel__custom__.kdl')
        self.assertEqual(mod.MANAGED_CONFIG.parent.name, 'niri')
        original = '// Existing personal rules remain untouched.\ndebug {\n' + mod.OFF + '}\n'
        active = mod.render_override(original, True)
        self.assertEqual(mod.render_override(active, False), original)

    def test_only_owned_flag_is_toggled_and_other_settings_survive(self):
        import remote_panel as mod
        self.assertTrue(hasattr(mod, 'render_override'), 'Safe config toggle is not implemented')
        original = 'debug {\n    honor-xdg-activation-with-invalid-serial\n    // remote-panel-managed: keep-laptop-panel-on-when-lid-is-closed\n}\n'
        active = mod.render_override(original, True)
        self.assertIn('    keep-laptop-panel-on-when-lid-is-closed // remote-panel-managed\n', active)
        self.assertEqual(mod.render_override(active, False), original)
        self.assertEqual(mod.render_override(active, True), active)
        with self.assertRaises(ValueError):
            mod.render_override('debug {}', True)
        with self.assertRaises(ValueError):
            mod.render_override(original + original, True)

class SocketTests(unittest.TestCase):
    def test_owned_udp_socket_presence(self):
        import remote_panel as mod
        import os
        import socket
        self.assertTrue(hasattr(mod, 'owned_udp_ports'), 'Owned stream socket detection is not implemented')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            self.assertIn(port, mod.owned_udp_ports(os.getpid()))
        self.assertNotIn(port, mod.owned_udp_ports(os.getpid()))
        self.assertEqual(mod.owned_udp_ports(99999999), set())

class RuntimeTests(unittest.TestCase):
    def test_runtime_can_restore_original_policy_without_vnc_server(self):
        import remote_panel as mod
        import tempfile
        self.assertTrue(hasattr(mod, 'PanelRuntime'), 'Panel runtime actuator is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.kdl'
            config.write_text('debug {\n' + mod.ON + '}\n')
            runtime = mod.PanelRuntime(config, str(Path(directory)/'absent.sock'), run=lambda *args: '')
            runtime.apply(False, False)
            self.assertIn(mod.OFF, config.read_text())
            self.assertNotIn(mod.ON, config.read_text())

class SunshineTests(unittest.TestCase):
    def test_only_sunshine_owned_video_and_audio_sockets_count(self):
        import remote_panel as mod
        self.assertTrue(hasattr(mod, 'stream_ports_active'), 'Streaming socket classifier is not implemented')
        self.assertTrue(mod.stream_ports_active({47998, 47999, 48000}, 47989))
        self.assertFalse(mod.stream_ports_active({47989, 47990, 48010}, 47989))
        self.assertFalse(mod.stream_ports_active({47999}, 47989))
        self.assertTrue(mod.stream_ports_active({50009, 50011}, 50000))

class OutputLeaseTests(unittest.TestCase):
    def test_external_outputs_restore_exact_original_state(self):
        import remote_panel as mod
        import tempfile
        self.assertTrue(hasattr(mod, 'OutputLease'), 'External screen snapshot/restore is not implemented')
        outputs = {
            'eDP-2': {'name': 'eDP-2', 'current_mode': 0, 'logical': {'x': 0, 'y': 0, 'scale': 1.5, 'transform': 'Normal'}},
            'HDMI-A-1': {'name': 'HDMI-A-1', 'make': 'Test', 'model': 'Monitor', 'serial': 'one', 'current_mode': 0,
                         'modes': [{'width': 2560, 'height': 1440, 'refresh_rate': 143995}],
                         'logical': {'x': -2560, 'y': 80, 'scale': 1.0, 'transform': 'Normal'}},
            'DP-1': {'name': 'DP-1', 'make': 'Other', 'model': 'Monitor', 'serial': 'two', 'current_mode': None, 'logical': None},
        }
        calls = []
        def run(*args):
            if args == ('niri', 'msg', '--json', 'outputs'):
                import json
                return json.dumps(outputs)
            calls.append(args)
            if args[-1] == 'off':
                outputs[args[3]]['current_mode'] = None
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory)/'outputs.json'
            lease = mod.OutputLease(snapshot, run=run)
            lease.acquire()
            lease.acquire()
            self.assertIsNone(outputs['HDMI-A-1']['current_mode'])
            self.assertEqual(len([c for c in calls if c[-1] == 'off' and c[3] == 'HDMI-A-1']), 1)
            saved = snapshot.read_text()
            lease = mod.OutputLease(snapshot, run=run)
            lease.acquire()
            self.assertEqual(snapshot.read_text(), saved)
            lease.release()
            self.assertIn(('niri','msg','output','HDMI-A-1','on'), calls)
            self.assertIn(('niri','msg','output','HDMI-A-1','mode','2560x1440@143.995'), calls)
            self.assertIn(('niri','msg','output','HDMI-A-1','position','set','--','-2560','80'), calls)
            self.assertNotIn(('niri','msg','output','DP-1','on'), calls)
            self.assertFalse(snapshot.exists())

    def test_moonlight_start_and_stop_never_move_outputs(self):
        import remote_panel as mod
        import tempfile
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.kdl'
            config.write_text('debug {\n' + mod.OFF + '}\n')
            run = lambda *args: calls.append(args)
            runtime = mod.PanelRuntime(config, str(root / 'absent.sock'), run=run,
                                        output_lease=mod.OutputLease(root / 'outputs.json', run=run))
            policy = mod.ConnectionPolicy(runtime.apply)
            policy.update(vnc=0, moonlight=0)
            policy.update(vnc=0, moonlight=1)
            policy.update(vnc=0, moonlight=0)
            self.assertEqual(calls, [], 'Moonlight must not mutate layout after capture initialization')
            self.assertIn(mod.OFF, config.read_text())

if __name__ == '__main__':
    unittest.main()
