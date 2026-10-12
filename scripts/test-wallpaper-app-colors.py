#!/usr/bin/env python3
"""Exercise Kitty and NyxMellow palette renderers with isolated HOME and commands."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
II = Path(os.environ['II_TEST_ROOT']) if os.environ.get('II_TEST_ROOT') else None
PYTHON = Path(os.environ.get('INIR_VENV', str(Path.home()/'.local/state/inir/.venv'))) / 'bin/python3'

class AppColorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='inir-app-palette-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        binary = self.home/'bin'
        binary.mkdir()
        for name in ['busctl','pkill']:
            path = binary/name
            path.write_text('#!/usr/bin/env python3\nimport os,json,sys\nwith open(os.environ["COMMAND_LOG"],"a") as f:f.write(json.dumps([sys.argv[0].split("/")[-1]]+sys.argv[1:])+"\\n")\n')
            path.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home/'.config'), XDG_STATE_HOME=str(self.home/'.local/state'), XDG_DATA_HOME=str(self.home/'.local/share'), XDG_CACHE_HOME=str(self.home/'.cache'), INIR_CONFIG_DIR=str(self.home/'.config/inir'), COMMAND_LOG=str(self.home/'commands'), PATH=str(binary)+':'+os.environ['PATH'])
        self.env.pop('INIR_INSTALL_SHARED_APP_CONFIGS', None)

    def run_command(self, command):
        r = subprocess.run(command, env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)
        return r.stdout

    def check_fcitx(self, palette):
        theme = self.home/'.local/share/fcitx5/themes/nyxmellow'
        files = {name:(theme/name).read_text() for name in ['theme.conf','panel.svg','highlight.svg']}
        for content in files.values():
            self.assertNotIn('{{', content)
        self.assertIn(palette['on_surface'].lower(), files['theme.conf'].lower())
        self.assertIn(palette['primary'].lower(), files['highlight.svg'].lower())
        self.assertRegex(files['panel.svg'], r'fill:#[0-9A-Fa-f]{6};')
        return files

    def test_personal_app_preferences_apply_even_when_weather_is_already_disabled(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('personal_session_config', ROOT/'scripts/personal/configure-session.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        directory = self.home/'.config/inir'
        directory.mkdir(parents=True)
        config = directory/'config.json'
        original = {'bar':{'weather':{'enable':False}},'iris':{'appearance':{'materialForApps':True,'accentForApps':True,'accent':'blue'}},'unrelated':{'keep':42}}
        config.write_text(json.dumps(original))
        module.configure_shell_preferences(directory)
        updated = json.loads(config.read_text())
        self.assertFalse(updated['iris']['appearance']['materialForApps'])
        self.assertFalse(updated['iris']['appearance']['accentForApps'])
        self.assertEqual(updated['iris']['appearance']['accent'],'blue')
        self.assertEqual(updated['unrelated'],original['unrelated'])
        first = config.read_bytes()
        module.configure_shell_preferences(directory)
        self.assertEqual(config.read_bytes(), first)

    def test_inir_wallpaper_palette_changes_kitty_and_fcitx_preserving_base_config(self):
        if not PYTHON.is_file(): self.skipTest('iNiR palette virtualenv is not installed')
        templates = self.home/'templates'
        shutil.copytree(ROOT/'defaults/matugen/templates/fcitx5', templates/'templates/fcitx5')
        manifest = json.loads((ROOT/'defaults/matugen/templates.json').read_text())
        manifest['templates'] = [x for x in manifest['templates'] if x['input'].startswith('fcitx5/')]
        self.assertEqual(len(manifest['templates']), 3)
        (templates/'templates.json').write_text(json.dumps(manifest))
        kitty = self.home/'.config/kitty/kitty.conf'
        kitty.parent.mkdir(parents=True)
        original = 'shell zsh\nfont_size 13\nglobinclude ../../.local/state/quickshell/user/generated/terminal/kitty-theme.conf\n'
        kitty.write_text(original)
        samples = []
        for color in ['#e03452','#2288cc']:
            self.run_command([str(PYTHON),str(ROOT/'scripts/colors/generate_colors_material.py'),'--color',color,'--mode','dark','--termscheme',str(ROOT/'scripts/colors/terminal/scheme-base.json'),'--json-output',str(self.home/'colors.json'),'--terminal-output',str(self.home/'terminal.json'),'--scss-output',str(self.home/'material_colors.scss'),'--render-templates',str(templates)])
            palette = json.loads((self.home/'colors.json').read_text())
            fcitx = self.check_fcitx(palette)
            self.run_command([sys.executable,str(ROOT/'scripts/colors/generate_terminal_configs.py'),'--scss',str(self.home/'material_colors.scss'),'--terminal-json',str(self.home/'terminal.json'),'--colors',str(self.home/'colors.json'),'--terminals','kitty'])
            generated = (self.home/'.local/state/quickshell/user/generated/terminal/kitty-theme.conf').read_text()
            terminal = json.loads((self.home/'terminal.json').read_text())
            self.assertRegex(generated, r'background\s+'+re.escape(terminal['term0']))
            self.assertEqual(kitty.read_text(),original)
            self.run_command(['bash',str(ROOT/'scripts/colors/modules/25-fcitx5.sh')])
            samples.append((terminal['term0'],fcitx['highlight.svg']))
        self.assertNotEqual(samples[0][0],samples[1][0])
        self.assertNotEqual(samples[0][1],samples[1][1])
        calls=[json.loads(x) for x in (self.home/'commands').read_text().splitlines()]
        self.assertEqual([x for x in calls if x[0]=='busctl'], [['busctl','--user','--auto-start=no','call','org.fcitx.Fcitx5','/controller','org.fcitx.Fcitx.Controller1','ReloadAddonConfig','s','classicui']]*2)
        self.assertIn(['pkill','--signal','SIGUSR1','-x','kitty'],calls)

    def test_ii_matugen_changes_fcitx_and_reloads_only_running_classicui(self):
        if II is None or not shutil.which('matugen'): self.skipTest('set II_TEST_ROOT to test the II renderer')
        source=II/'dots/.config/matugen'
        table=tomllib.loads((source/'config.toml').read_text())['templates']
        definitions={k:v for k,v in table.items() if k.startswith('fcitx5_')}
        self.assertEqual(len(definitions),3)
        config='[config]\nversion_check = false\n'
        for key,value in definitions.items():
            template=source/'templates/fcitx5'/Path(value['input_path']).name
            output=self.home/'.local/share/fcitx5/themes/nyxmellow'/Path(value['output_path']).name
            config+=f'\n[templates.{key}]\ninput_path = {json.dumps(str(template))}\noutput_path = {json.dumps(str(output))}\n'
        conf=self.home/'matugen.toml';conf.write_text(config)
        samples=[]
        for color in ['#e03452','#2288cc']:
            self.run_command(['matugen','--config',str(conf),'color','hex',color,'--mode','dark'])
            theme=self.home/'.local/share/fcitx5/themes/nyxmellow'
            contents=[(theme/name).read_text() for name in ['theme.conf','panel.svg','highlight.svg']]
            self.assertFalse(any('{{' in x for x in contents))
            samples.append(contents)
        self.assertNotEqual(samples[0],samples[1])
        (self.home/'.config/quickshell/ii').mkdir(parents=True)
        settings=self.home/'.config/illogical-impulse/config.json';settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'appearance':{'wallpaperTheming':{'enableTerminal':False},'openrgb':{'enable':False}}}))
        scss=self.home/'.local/state/quickshell/user/generated/terminal/material_colors.scss';scss.parent.mkdir(parents=True)
        scss.write_text('$term0: #112233;\n')
        self.run_command(['bash',str(II/'dots/.config/quickshell/ii/scripts/colors/applycolor.sh')])
        calls=[json.loads(x) for x in (self.home/'commands').read_text().splitlines()]
        self.assertEqual(calls,[['busctl','--user','--auto-start=no','call','org.fcitx.Fcitx5','/controller','org.fcitx.Fcitx.Controller1','ReloadAddonConfig','s','classicui']])

if __name__=='__main__': unittest.main()
