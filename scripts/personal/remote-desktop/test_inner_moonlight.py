"""Regression tests for repeatable, fail-closed AMD inner streaming."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).with_name('inner_moonlight.py')

def load():
    spec = importlib.util.spec_from_file_location('inner_moonlight', PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class InnerMoonlightTests(unittest.TestCase):
    def test_idle_external_only_is_rejected(self):
        mod = load()
        self.assertFalse(mod.inner_only_ready({'eDP-2': {'current_mode': None, 'logical': None},
                                               'HDMI-A-1': {'current_mode': 0, 'logical': {'x': 0, 'y': 0}}}))

    def test_both_enabled_is_rejected_even_with_inner_at_origin(self):
        mod = load()
        d = {'eDP-2': {'current_mode': 0, 'logical': {'x': 0, 'y': 0}},
             'HDMI-A-1': {'current_mode': 0, 'logical': {'x': 1706, 'y': 0}}}
        self.assertFalse(mod.inner_only_ready(d))
        d['HDMI-A-1']['current_mode'] = None
        d['HDMI-A-1']['logical'] = None
        self.assertTrue(mod.inner_only_ready(d))
        d['eDP-2']['logical']['x'] = -1
        self.assertFalse(mod.inner_only_ready(d))

    def test_cleanup_stops_sunshine_and_never_restarts_it(self):
        mod = load()
        calls = []
        class Runtime:
            def shutdown(self):
                calls.append(('restore-displays',))
        mod.cleanup(Runtime(), lambda *args: calls.append(args))
        self.assertEqual(calls, [('stop', mod.UNIT), ('restore-displays',), ('start', mod.CONTROLLER)])

    def test_failed_sunshine_stop_must_not_restore_external_capture_target(self):
        mod = load()
        calls = []
        class Runtime:
            def shutdown(self):
                calls.append('unsafe-restoration')
        def manage(*args):
            raise RuntimeError('Sunshine stop failed')
        with self.assertRaises(RuntimeError):
            mod.cleanup(Runtime(), manage)
        self.assertEqual(calls, [])

    def test_prep_deadline_and_disconnect_lifetimes(self):
        mod = load()
        policy = mod.SessionPolicy(10, 5)
        self.assertTrue(policy.hold(14, False, 0))
        self.assertFalse(policy.hold(15, False, 0))
        policy = mod.SessionPolicy(10, 5)
        self.assertTrue(policy.hold(11, True, 0))
        self.assertTrue(policy.hold(600, True, 1))
        self.assertTrue(policy.hold(601, False, 1))
        self.assertTrue(policy.hold(602, False, 0))
        self.assertFalse(policy.hold(604, False, 0))

    def test_idle_status_blocks_capture_even_before_niri_reload_finishes(self):
        mod = load()
        self.assertFalse(mod.manager_is_preparing({'state': 'idle', 'manager_pid': 42}, 42))
        self.assertFalse(mod.manager_is_preparing({'state': 'restoring', 'manager_pid': 42}, 42))
        self.assertFalse(mod.manager_is_preparing({'state': 'ready', 'manager_pid': 42}, 0))
        self.assertTrue(mod.manager_is_preparing({'state': 'starting-capture', 'manager_pid': 42}, 42))
        self.assertTrue(mod.manager_is_preparing({'state': 'ready', 'manager_pid': 42}, 42))

    def test_prepare_wakes_only_verified_inner_layout_and_waits_for_kernel(self):
        import tempfile
        mod = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            connector = root / 'card7-eDP-2'
            connector.mkdir()
            (connector / 'enabled').write_text('disabled\n')
            (connector / 'dpms').write_text('Off\n')
            layout = {'eDP-2': {'current_mode': 0, 'logical': {'x': 0, 'y': 0}}}
            calls = []
            def run(*args):
                calls.append(args)
                (connector / 'enabled').write_text('enabled\n')
                (connector / 'dpms').write_text('On\n')
            mod.ensure_inner_powered(lambda: layout, run, root)
            self.assertEqual(calls, [('niri', 'msg', 'action', 'power-on-monitors')])
            self.assertTrue(mod.inner_powered(root))
            layout['HDMI-A-1'] = {'current_mode': 0, 'logical': {'x': 0, 'y': 0}}
            with self.assertRaises(RuntimeError):
                mod.ensure_inner_powered(lambda: layout, run, root)
            self.assertEqual(len(calls), 1)
            (connector / 'dpms').write_text('Off\n')
            self.assertFalse(mod.inner_powered(root))
            layout.pop('HDMI-A-1')
            with self.assertRaises(RuntimeError):
                mod.ensure_inner_powered(lambda: layout, lambda *a: None, root, timeout=0)

    def test_http_listening_is_not_encoder_readiness(self):
        mod = load()
        self.assertFalse(mod.capture_probe_ready('Starting main loop'))
        self.assertFalse(mod.capture_probe_ready('Unable to initialize capture method\nStarting main loop'))
        healthy = 'Screencasting with KMS\nFound H.264 encoder: h264_vaapi [vaapi]\nStarting main loop'
        self.assertTrue(mod.capture_probe_ready(healthy))
        self.assertFalse(mod.capture_probe_ready(healthy + '\nFatal: Capture failed'))

    def test_fixed_config_rejects_external_and_nvenc(self):
        mod = load()
        good = 'capture = kms\nencoder = vaapi\nadapter_name = /dev/dri/renderD128\noutput_name = eDP-2\n'
        mod.validate_config(good)
        for bad in [good.replace('eDP-2', 'HDMI-A-1'), good.replace('vaapi', 'nvenc')]:
            with self.assertRaises(ValueError):
                mod.validate_config(bad)

if __name__ == '__main__':
    unittest.main()
