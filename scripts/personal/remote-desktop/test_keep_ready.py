"""Small policy tests for an opt-in always-ready internal panel."""
import json
from pathlib import Path
import tempfile
import unittest
import remote_panel as panel


class ReadyPanelTests(unittest.TestCase):
    def test_idle_keeps_internal_available_without_disabling_external(self):
        calls = []
        outputs = {'eDP-2': {'current_mode': 0}, 'HDMI-A-1': {'current_mode': 0}}
        def run(*args):
            calls.append(args)
            if args == ('niri', 'msg', '--json', 'outputs'):
                return json.dumps(outputs)
            return ''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root/'config.kdl'
            config.write_text('debug {\n' + panel.OFF + '}\n')
            runtime = panel.PanelRuntime(config, str(root/'absent.sock'), run=run, keep_ready=True)
            runtime.apply(False, False)
            self.assertIn(panel.ON, config.read_text())
            self.assertIn(('niri', 'msg', 'output', 'eDP-2', 'on'), calls)
            self.assertNotIn(('niri', 'msg', 'output', 'HDMI-A-1', 'off'), calls)

    def test_command_line_exposes_ready_mode(self):
        import os
        import subprocess
        env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1000')
        result = subprocess.run(['/usr/bin/python3', str(Path(panel.__file__)), '--help'],
                                env=env, capture_output=True, text=True, check=True)
        self.assertIn('--keep-panel-ready', result.stdout)

    def test_shutdown_restores_lid_policy_even_in_ready_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root/'config.kdl'
            config.write_text('debug {\n' + panel.ON + '}\n')
            runtime = panel.PanelRuntime(config, str(root/'absent.sock'), run=lambda *args: '', keep_ready=True)
            runtime.shutdown()
            self.assertIn(panel.OFF, config.read_text())

    def test_startup_gate_rejects_external_only_and_accepts_internal(self):
        import importlib.util
        module_path = Path(panel.__file__).with_name('wait_inner_ready.py')
        self.assertTrue(module_path.exists(), 'Sunshine internal-output startup gate is missing')
        spec = importlib.util.spec_from_file_location('wait_inner_ready', module_path)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        external_only = {'HDMI-A-1': {'current_mode': 0, 'logical': {}},
                         'eDP-2': {'current_mode': None, 'logical': None}}
        with self.assertRaisesRegex(RuntimeError, 'refusing'):
            gate.wait_ready(timeout=0, read_outputs=lambda: external_only)
        self.assertTrue(gate.wait_ready(timeout=0, read_outputs=lambda: {
            'eDP-2': {'current_mode': 0, 'logical': {}}}))

    def test_cgroup_socket_detection_is_exact_and_ignores_other_services(self):
        self.assertTrue(hasattr(panel, 'cgroup_udp_ports'), 'Cgroup socket detection is missing')
        group = '/user.slice/app-dev.lizardbyte.app.Sunshine.service'
        text = '\n'.join([
            f'UNCONN 0 0 0.0.0.0:47998 0.0.0.0:* cgroup:{group}',
            f'UNCONN 0 0 [::]:48000 [::]:* cgroup:{group}',
            f'UNCONN 0 0 0.0.0.0:48001 0.0.0.0:* cgroup:{group}-other',
            'UNCONN 0 0 0.0.0.0:12345 0.0.0.0:*',
        ])
        self.assertEqual(panel.cgroup_udp_ports(text, group), {47998, 48000})
        self.assertEqual(panel.cgroup_udp_ports(text, ''), set())
        self.assertEqual(panel.cgroup_udp_ports(text, '/different.service'), set())


if __name__ == '__main__':
    unittest.main()
