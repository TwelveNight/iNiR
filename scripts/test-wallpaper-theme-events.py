#!/usr/bin/env python3
"""Run the real ThemeService with isolated wallpaper events and command capture."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WallpaperThemeTests(unittest.TestCase):
    def test_external_wallpaper_events_regenerate_once_without_config_write(self):
        for standalone in (False, True):
            with self.subTest(standalone=standalone), tempfile.TemporaryDirectory(prefix='inir-theme-event-') as tmp:
                base = Path(tmp)
                (base / 'services').mkdir()
                (base / 'modules/common').mkdir(parents=True)
                (base / 'runtime').mkdir(mode=0o700)
                recorder = base / 'switchwall'
                recorder.write_text('#!/usr/bin/env python3\nimport os,json,sys\nwith open(os.environ["THEME_CALLS"],"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\n')
                recorder.chmod(0o755)
                def singleton(directory, name, body):
                    (base / directory / (name + '.qml')).write_text('pragma Singleton\nimport QtQuick\nQtObject { ' + body + ' }\n')
                    with (base / directory / 'qmldir').open('a') as f:
                        f.write('singleton ' + name + ' 1.0 ' + name + '.qml\n')
                shutil.copy2(ROOT / 'services/ThemeService.qml', base / 'services/ThemeService.qml')
                (base / 'services/qmldir').write_text('singleton ThemeService 1.0 ThemeService.qml\n')
                singleton('modules/common', 'Config', 'property bool ready: false; property var options: ({appearance:{theme:"auto",wallpaperTheming:{enableVesktop:false}},panelFamily:"ii"}); signal configChanged(); function setNestedValue(k,v) {}')
                singleton('modules/common', 'Appearance', 'property var m3colors: ({darkmode:true,m3primary:"#aabbcc"}); function toggleDarkMode() {}')
                singleton('modules/common', 'Directories', 'property string wallpaperSwitchScriptPath: ' + json.dumps(str(recorder)) + '; property string scriptsPath: "/unused"')
                singleton('services', 'Wallpapers', 'property bool skwdBackendEnabled: true; property string activeWallpaperPath: "/initial.png"; property string effectiveWallpaperPath: activeWallpaperPath; property bool _applyInProgress: false; function currentThemingWallpaperPath() { return activeWallpaperPath }')
                singleton('services', 'ThemePresets', 'function applyPreset() {}')
                singleton('services', 'MaterialThemeLoader', 'function reapplyTheme() {} function requestExternalApply() {}')
                (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.common
ShellRoot {
 property bool initialized: ThemeService.isAutoTheme
 property int stage: 0
 Timer { running: true; repeat: true; interval: 1100
  onTriggered: {
   if (parent.stage === 0) Config.ready = true
   if (parent.stage === 1) Wallpapers.activeWallpaperPath = "/new.png"
   if (parent.stage === 2) { Wallpapers.activeWallpaperPath = "/new.png"; Config.configChanged() }
   if (parent.stage === 3) Wallpapers.activeWallpaperPath = "/latest.mp4"
   if (parent.stage === 4) Config.options = {appearance:{theme:"custom",wallpaperTheming:{enableVesktop:false}},panelFamily:"ii"}
   if (parent.stage === 5) Wallpapers.activeWallpaperPath = "/manual-theme.png"
   if (parent.stage === 6) Qt.quit()
   parent.stage++
  }
 }
}''')
                env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=str(base/'config'), XDG_STATE_HOME=str(base/'state'), XDG_CACHE_HOME=str(base/'cache'), XDG_RUNTIME_DIR=str(base/'runtime'), QT_QPA_PLATFORM='offscreen', THEME_CALLS=str(base/'calls'), INIR_STANDALONE_WINDOW='1' if standalone else '0')
                result = subprocess.run(['qs','-p',tmp,'--no-color'], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('TypeError', result.stdout)
                self.assertNotIn('is not defined', result.stdout)
                calls = [json.loads(line) for line in (base/'calls').read_text().splitlines()] if (base/'calls').exists() else []
                self.assertEqual(calls, [] if standalone else [['--noswitch','--image','/new.png'],['--noswitch','--image','/latest.mp4']], result.stdout)

if __name__ == '__main__':
    unittest.main()
