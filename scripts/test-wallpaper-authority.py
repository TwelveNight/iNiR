#!/usr/bin/env python3
"""Verify desktop state authority using real QML and isolated skwd responses."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WallpaperAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inir-wall-authority-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        for folder in ["services", "modules/common/functions", "bin", "runtime"]:
            (self.base / folder).mkdir(parents=True)
        (self.base / "runtime").chmod(0o700)
        self.env = dict(os.environ, HOME=str(self.base), QT_QPA_PLATFORM="offscreen",
                        XDG_RUNTIME_DIR=str(self.base / "runtime"), XDG_CONFIG_HOME=str(self.base / "config"),
                        XDG_CACHE_HOME=str(self.base / "cache"), XDG_STATE_HOME=str(self.base / "state"),
                        MOCK_DIR=str(self.base), PATH=str(self.base / "bin") + ":" + os.environ["PATH"])

    def executable(self, name, text):
        p = self.base / "bin" / name
        p.write_text(text)
        p.chmod(0o755)

    def singleton(self, folder, name, text):
        p = self.base / folder
        (p / f"{name}.qml").write_text(text)
        with (p / "qmldir").open("a") as f:
            f.write(f"singleton {name} 1.0 {name}.qml\n")

    def test_real_listener_and_resolvers_follow_external_multimonitor_state(self):
        for name in ["SkwdBackend", "WallpaperListener"]:
            self.singleton("services", name, (ROOT / f"services/{name}.qml").read_text())
        (self.base / "services/skwdState.js").write_text((ROOT / "services/skwdState.js").read_text())
        def stub(folder, name, body):
            self.singleton(folder, name, 'pragma Singleton\nimport QtQuick\nQtObject {\n' + body + '\n}\n')
        stub("modules/common", "Directories", 'property string homePath: "/fixture"')
        stub("modules/common", "Config", '''property var options: ({background: {
            wallpaperPath: "/stale.png", multiMonitor:{enable:false}, wallpapersByMonitor:[]},
            appearance:{wallpaperTheming:{useBackdropForColors:true}}})
            signal configChanged()''')
        stub("services", "CompositorService", 'property bool isNiri: true; property bool isHyprland: false')
        stub("services", "NiriService", 'property string currentOutput: "HDMI-A-1"')
        stub("modules/common/functions", "FileUtils", 'function trimFileProtocol(p) { return p }')
        # Use the production resolver functions, so this exercises the early
        # skwd branch even with deliberately conflicting saved backdrop settings.
        source = (ROOT / "services/Wallpapers.qml").read_text()
        functions = []
        for name in ["currentMainWallpaperPath", "currentThemingWallpaperPath"]:
            start = source.index(f"    function {name}(")
            end = source.index("\n    }", start) + len("\n    }")
            functions.append(source[start:end])
        self.singleton("services", "Wallpapers", '''pragma Singleton
import QtQuick
import qs.modules.common
import qs.services
QtObject {
 id: root
 property bool skwdBackendEnabled: true
 function stillUrlFor(path) { return path ? "file://" + path : "" }
''' + '\n'.join(functions) + '\n}\n')
        self.executable("skwd-helm", '''#!/usr/bin/env python3
import os,json,time,sys
from pathlib import Path
p=Path(os.environ['MOCK_DIR'])
if sys.argv[1]=='current':
 print(json.dumps({'outputs':[
  {'name':'HDMI-A-1','connected':True,'path':'/external.gif' if (p/'event').exists() else '/desktop.mp4'},
  {'name':'eDP-2','connected':True,'path':'/still.png'},
  {'name':'unplugged','connected':False,'path':'/obsolete.png'}]}))
elif sys.argv[1]=='watch':
 time.sleep(1)
 (p/'event').touch()
 print(json.dumps({'event':'skwd.wall.applied'}),flush=True)
 time.sleep(20)
else: sys.exit(9)
''')
        (self.base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
ShellRoot {
 id: root
 property int stage: 0
 function check(condition, label) { if (!condition) { console.error("FAIL " + label); Qt.quit() } }
 Timer { running:true; repeat:true; interval:50; onTriggered: {
  if (!SkwdBackend.available) return
  const map=WallpaperListener.effectivePerMonitor
  if (!map["HDMI-A-1"]) return
  if (root.stage===0) {
   root.check(Wallpapers.currentMainWallpaperPath()==="/desktop.mp4", "focused output")
   root.check(Wallpapers.currentThemingWallpaperPath()==="/desktop.mp4", "color source")
   root.check(Wallpapers.currentMainWallpaperPath("eDP-2")==="/still.png", "per-output still")
   root.check(map["HDMI-A-1"].isVideo && !map["unplugged"], "active output map")
   NiriService.currentOutput="eDP-2"
   root.check(Wallpapers.currentMainWallpaperPath()==="/still.png", "focus change")
   NiriService.currentOutput="HDMI-A-1"
   root.stage=1
  } else if (map["HDMI-A-1"].path==="/external.gif") {
   root.check(Wallpapers.currentThemingWallpaperPath()==="/external.gif", "external change")
   root.check(map["HDMI-A-1"].isGif, "gif type")
   SkwdBackend.available=false
   root.check(Wallpapers.currentMainWallpaperPath()==="/external.gif", "last good daemon reply")
   console.log("PASS authoritative desktop paths")
   Qt.quit()
  }
 } }
}''')
        result = subprocess.run(["qs", "-p", str(self.base), "--no-color"], env=self.env,
                                capture_output=True, text=True, timeout=10)
        output = result.stdout + result.stderr
        self.assertIn("PASS authoritative desktop paths", output, output)
        for error in ["FAIL", "ReferenceError", "TypeError", "binding loop"]:
            self.assertNotIn(error, output, output)

    def run_palette_source(self, path, family="ii", stale_thumbnail=""):
        source = (ROOT / "scripts/colors/switchwall.sh").read_text()
        functions = []
        for name in ["switch", "resolve_effective_theming_wallpaper", "is_video", "is_gif", "has_valid_file"]:
            start = source.index(f"{name}() {{")
            end = source.index("\n}", start) + 2
            if name == "resolve_effective_theming_wallpaper":
                end = source.index("\n }", start) + 3
            functions.append(source[start:end])
        backdrop = self.base / "old-backdrop.png"
        backdrop.write_text("synthetic old backdrop")
        response = self.base / "state.json"
        response.write_text(json.dumps({"outputs": [{"name": "eDP-2", "path": str(path), "connected": True}]}))
        self.executable("skwd-helm", '#!/bin/sh\n[ "$1 $2" = "current --json" ] || exit 9\ncat "$MOCK_DIR/state.json"\n')
        self.executable("hyprctl", "#!/bin/sh\nexit 1\n")
        script = '\n'.join(functions) + r'''
get_focused_monitor_name() { echo eDP-2; }
check_and_prompt_upscale() { :; }
remove_restore() { :; }
extract_representative_frame() { printf 'synthetic preview' > "$2"; }
pre_process() { printf '%s\n' "${generate_colors_material_args[@]}" > "$MOCK_DIR/palette-args"; }
write_generated_wallpaper_path() { :; }
cfg_use_backdrop=true
cfg_ii_backdrop_use_main=false
cfg_waffle_backdrop_use_main=false
cfg_ii_backdrop_path="$MOCK_DIR/old-backdrop.png"
cfg_waffle_backdrop_path="$MOCK_DIR/old-backdrop.png"
cfg_panel_family="$1"
cfg_thumbnail_path="$2"
cfg_enable_apps_shell=false
cfg_enable_terminal=false
THUMBNAIL_DIR="$MOCK_DIR/thumbnails"
switch "" dark auto "" "" 1 1
'''
        result = subprocess.run(["bash", "-c", script, "palette-probe", family, str(stale_thumbnail)],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return (self.base / "palette-args").read_text().splitlines()

    def test_cli_palette_ignores_saved_backdrop_after_daemon_resolution(self):
        active = self.base / "active.png"
        active.write_text("synthetic active wallpaper")
        for family in ["ii", "waffle", "iris"]:
            with self.subTest(family=family):
                args = self.run_palette_source(active, family)
                self.assertEqual(args[args.index("--path") + 1], str(active))

    def test_cli_video_preview_belongs_to_active_wallpaper_not_saved_config(self):
        active = self.base / "active video.mp4"
        active.write_text("synthetic video")
        stale = self.base / "old-preview.jpg"
        stale.write_text("synthetic stale preview")
        args = self.run_palette_source(active, stale_thumbnail=str(stale))
        expected = self.base / "thumbnails" / (hashlib.md5(str(active).encode()).hexdigest() + ".jpg")
        self.assertEqual(args[args.index("--path") + 1], str(expected))
        self.assertTrue(expected.is_file())

    def test_cli_color_resolution_uses_daemon_and_refuses_failure(self):
        source = (ROOT / "scripts/colors/switchwall.sh").read_text()
        start = source.index(" resolve_effective_theming_wallpaper() {")
        end = source.index("\n }", start) + len("\n }")
        resolver = source[start:end]
        response = self.base / "state.json"
        self.executable("skwd-helm", '#!/bin/sh\n[ "$1 $2" = "current --json" ] || exit 9\ncat "$MOCK_DIR/state.json"\n')
        command = ["bash", "-c", resolver + '\nget_focused_monitor_name() { echo eDP-2; }; resolve_effective_theming_wallpaper']
        for suffix in ["png", "mp4", "gif"]:
            path = f'/external wallpaper $name.{suffix}'
            response.write_text(json.dumps({"outputs": [{"name":"eDP-2", "path":path, "connected":True}]}))
            result = subprocess.run(command, env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), path)
        response.write_text('{"outputs":[]}')
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.executable("skwd-helm", '#!/bin/sh\nexit 7\n')
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
