#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('watch', Path(__file__).with_name('wallpaper') / 'skwd-output-watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
ON = {'current_mode': 0, 'logical': {'scale': 1, 'width': 2560, 'height': 1440}}
OFF = {'current_mode': None, 'logical': None}


class WatchTests(unittest.TestCase):
    def test_initial_snapshot_and_disabling_do_not_reapply(self):
        state = watch.PendingOutputs()
        state.update({'HDMI': ON, 'eDP': ON}, 0)
        self.assertEqual(state.take(10), set())
        state.update({'HDMI': OFF, 'eDP': ON}, 11)
        self.assertEqual(state.take(20), set())

    def test_reenable_waits_for_final_hotplug_burst(self):
        state = watch.PendingOutputs()
        state.update({'HDMI': OFF, 'eDP': ON}, 0)
        state.update({'HDMI': ON, 'eDP': ON}, 1)
        state.update({'HDMI': ON, 'eDP': ON}, 3)
        self.assertEqual(state.take(4), set())
        self.assertEqual(state.take(6), {'HDMI'})
        self.assertEqual(state.take(7), set())

    def test_off_again_cancels_stale_restore(self):
        state = watch.PendingOutputs()
        state.update({'HDMI': OFF, 'eDP': ON}, 0)
        state.update({'HDMI': ON, 'eDP': ON}, 1)
        state.update({'HDMI': OFF, 'eDP': ON}, 2)
        self.assertEqual(state.take(6), set())

    def test_restore_uses_latest_path_and_explicit_target(self):
        data = {'outputs': [{'name': 'HDMI', 'connected': True, 'path': '/new wallpaper.mp4'},
                            {'name': 'eDP', 'connected': True, 'path': '/other.png'}]}
        with patch.object(watch.subprocess, 'check_output', side_effect=[json.dumps({'HDMI': ON}), '[]']), patch.object(watch.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,json.dumps(data))) as run:
            watch.restore({'HDMI'})
            self.assertEqual(run.call_args_list[1].args[0], ['skwd-helm','apply','/new wallpaper.mp4','-o','HDMI'])
            self.assertEqual(run.call_count,2)

    def test_missing_disconnected_outputs_are_not_applied(self):
        data = {'outputs': [{'name': 'HDMI', 'connected': False, 'path': '/wall.png'}]}
        with patch.object(watch.subprocess, 'check_output', side_effect=[json.dumps({'HDMI': ON}), '[]']), patch.object(watch.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,json.dumps(data))) as run:
            watch.restore({'HDMI'})
            self.assertEqual(run.call_count,1)

    def test_healthy_wallpaper_surface_is_not_restarted(self):
        data = {'outputs': [{'name': 'HDMI', 'connected': True, 'path': '/wall.png'}]}
        layers = [{'output': 'HDMI', 'namespace': 'skwd-wall-vk', 'layer': 'Background'}]
        with patch.object(watch.subprocess, 'check_output', side_effect=[json.dumps({'HDMI': ON}), json.dumps(layers)]), patch.object(watch.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,json.dumps(data))) as run:
            watch.restore({'HDMI'})
            self.assertEqual(run.call_count,1)


if __name__ == '__main__':
    unittest.main()
