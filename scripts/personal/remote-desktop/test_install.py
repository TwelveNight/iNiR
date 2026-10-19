"""Preserve each desktop's personal configuration entry during shared deployment."""
import json
from pathlib import Path
import tempfile
import unittest
import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.profiles = self.home / '.config/desktop-profiles'
        self.profiles.mkdir(parents=True)
        (self.profiles / 'profiles.json').write_text(json.dumps({
            'inir': {'compositor': 'niri'}, 'nyxuri': {'compositor': 'niri'}, 'hyprland-ii': {'compositor': 'hypr'}}))
        for profile, entry in [('inir', 'config.d/90-user-extra.kdl'), ('nyxuri', '__custom__.kdl')]:
            root = self.profiles / profile / 'niri'
            (root / entry).parent.mkdir(parents=True)
            (root / 'config.kdl').write_text(f'include "{entry}"\n')
            (root / entry).write_text('// keep personal content\n')

    def test_separate_preserved_entries_are_idempotent_and_hyprland_is_untouched(self):
        changes = install.profile_changes(self.home)
        self.assertEqual(len(changes), 4)
        for path, text in changes.items():
            path.write_text(text)
        self.assertEqual(install.profile_changes(self.home), {})
        for profile, entry in [('inir', 'config.d/90-user-extra.kdl'), ('nyxuri', '__custom__.kdl')]:
            root = self.profiles / profile / 'niri'
            self.assertIn('// keep personal content', (root / entry).read_text())
            self.assertIn('remote-panel__custom__.kdl', (root / entry).read_text())
        self.assertFalse((self.profiles / 'hyprland-ii').exists())

    def test_services_allow_the_manager_to_finish_probes_and_restore_before_killing_children(self):
        self.assertIn('KillMode=mixed', install.CONTROLLER_UNIT)
        self.assertIn('KillMode=mixed', install.GRACEFUL_DROPIN)
        self.assertIn('TimeoutStopSec=60', install.GRACEFUL_DROPIN)

    def test_unknown_entry_and_redirected_profile_are_rejected(self):
        root = self.profiles / 'nyxuri/niri'
        (root / 'config.kdl').write_text('// missing preserved include\n')
        with self.assertRaisesRegex(ValueError, 'preserved custom entry'):
            install.profile_changes(self.home)
        (root / 'config.kdl').write_text('include "__custom__.kdl"\n')
        root.rename(root.with_name('other'))
        root.symlink_to(root.with_name('other'))
        with self.assertRaisesRegex(ValueError, 'ordinary directory'):
            install.profile_changes(self.home)


if __name__ == '__main__':
    unittest.main()
