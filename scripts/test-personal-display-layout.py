#!/usr/bin/env python3
"""Regress duplicated output positions without changing capture geometry."""
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('display_layout', Path(__file__).parent / 'personal/display-layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class LayoutTests(unittest.TestCase):
    def test_positions_preserve_modes_scaling_and_nested_settings(self):
        source = '''output "eDP-2" {
    mode "2560x1600@165.004"
    scale 1.5
    position x=4267 y=397
    hot-corners {
        top-left
    }
}
output "HDMI-A-1" {
    mode "2560x1440@143.995"
    scale 1.0
    position x=1707 y=0
}
'''
        expected = source.replace('position x=4267 y=397', 'position x=0 y=0').replace(
            'position x=1707 y=0', 'position x=-2560 y=0')
        self.assertEqual(layout.position_outputs(source), expected)
        self.assertEqual(layout.position_outputs(expected), expected)

    def test_both_generated_and_root_definitions_are_updated(self):
        for source in ['output "HDMI-A-1" {\n    position x=1707 y=0\n}\n',
                       'include "monitor.kdl"\noutput "HDMI-A-1" {\n    position x=1707 y=0\n}\n']:
            self.assertIn('position x=-2560 y=0', layout.position_outputs(source))
        with self.assertRaises(ValueError):
            layout.position_outputs('', 0)


if __name__ == '__main__':
    unittest.main()
