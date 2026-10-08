#!/usr/bin/env python3
"""Keep upstream renderer-only controls out of the skwd-wall desktop UI."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkwdUpstreamUiTests(unittest.TestCase):
    def test_waffle_scaling_does_not_claim_to_control_skwd(self):
        source = (ROOT / "modules/waffle/settings/pages/WBackgroundPage.qml").read_text()
        scaling = re.search(r'WSettingsDropdown\s*\{([^{}]*?)label:\s*Translation\.tr\("Scaling"\)', source)
        if scaling is None:
            self.fail("Wallpaper scaling dropdown is missing")
        self.assertIn("visible: !Wallpapers.skwdBackendEnabled", scaling.group(1),
                      "Shell fillMode is not a skwd-wall command; hide the renderer-only dropdown")


if __name__ == "__main__":
    unittest.main()
