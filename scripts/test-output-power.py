#!/usr/bin/env python3
"""Exercise display power decisions with IPC doubles; never toggle real outputs."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('niri_config', Path(__file__).with_name('niri-config.py'))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
ON = {'current_mode': 0, 'logical': {'scale': 1.25, 'x': 2012, 'y': 143}}
OFF = {'current_mode': None, 'logical': None}


class PowerTests(unittest.TestCase):
    def invoke(self, states, name, action, failure=False):
        calls = []
        def ipc(*args):
            calls.append(args)
            if args == ('-j', 'outputs'):
                return json.dumps(states), 0
            if failure:
                return 'backend refused', 1
            states[name] = ON if action == 'on' else OFF
            return '', 0
        with patch.object(helper, 'run_niri', ipc):
            result = helper.set_output_power([name, action])
        return result, calls

    def test_last_active_cannot_be_disabled_even_with_connected_disabled_output(self):
        with self.assertRaisesRegex(ValueError, 'last active'):
            self.invoke({'external': ON, 'internal': OFF}, 'external', 'off')

    def test_disabled_output_can_be_enabled_and_zero_active_can_recover(self):
        for states in ({'internal': OFF, 'external': ON}, {'internal': OFF}):
            result, calls = self.invoke(states, 'internal', 'on')
            self.assertTrue(result['changed'])
            self.assertEqual(calls, [('-j', 'outputs'), ('output', 'internal', 'on'), ('-j', 'outputs')])

    def test_turn_off_one_of_two_without_changing_geometry(self):
        result, calls = self.invoke({'internal': ON, 'external': ON}, 'internal', 'off')
        self.assertTrue(result['success'])
        self.assertEqual(calls[1], ('output', 'internal', 'off'))
        self.assertEqual(len(calls), 3)

    def test_disconnected_display_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no longer connected'):
            self.invoke({'external': ON}, 'internal', 'on')

    def test_idempotent_does_not_send_output_command(self):
        result, calls = self.invoke({'external': ON}, 'external', 'on')
        self.assertFalse(result['changed'])
        self.assertEqual(calls, [('-j', 'outputs')])

    def test_failure_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'backend refused'):
            self.invoke({'external': ON, 'internal': OFF}, 'internal', 'on', True)

    def test_invalid_argument_does_not_issue_command(self):
        with patch.object(helper, 'run_niri') as ipc:
            with self.assertRaises(ValueError):
                helper.set_output_power(['external', 'position'])
            ipc.assert_not_called()

    def test_query_failure_does_not_issue_mutation(self):
        with patch.object(helper, 'run_niri', return_value=('IPC unavailable', 1)) as ipc:
            with self.assertRaisesRegex(ValueError, 'IPC unavailable'):
                helper.set_output_power(['external', 'off'])
            ipc.assert_called_once_with('-j', 'outputs')

    def test_success_requires_observed_state(self):
        with patch.object(helper, 'run_niri', side_effect=lambda *args: (json.dumps({'external': ON, 'internal': OFF}), 0)), patch.object(helper.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'not confirmed'):
                helper.set_output_power(['internal', 'on'])

    def test_command_reports_error_json(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(helper.os.environ, {'XDG_RUNTIME_DIR': temp}), patch.object(helper, 'set_output_power', side_effect=ValueError('last active')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(helper.cmd_output_power(['external', 'off']), 1)
            self.assertEqual(json.loads(output.getvalue()), {'error': 'last active'})


if __name__ == '__main__':
    unittest.main()
