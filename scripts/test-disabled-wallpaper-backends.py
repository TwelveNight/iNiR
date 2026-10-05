#!/usr/bin/env python3
"""Load the actual disabled backend QML; trap any attempted legacy subprocess."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="inir-inert-backend-") as tmp:
    base = Path(tmp)
    for folder in ["services", "modules/common/functions", "runtime"]:
        (base / folder).mkdir(parents=True)
    (base / "runtime").chmod(0o700)
    trap = base / "unexpected-process"
    trap.write_text('#!/bin/sh\nprintf "called\\n" >> "$BACKEND_PROCESS_LOG"\n')
    trap.chmod(0o755)
    for name in ["AwwwBackend", "WebWallpaper"]:
        # Substitute only the executable, leaving real QML lifecycle/guards intact.
        source = (ROOT / f"services/{name}.qml").read_text().replace('"/usr/bin/bash"', f'"{trap}"')
        (base / f"services/{name}.qml").write_text(source)
    def singleton(folder, name, body):
        dest = base / folder
        (dest / f"{name}.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject {\n' + body + '\n}\n')
        with (dest / "qmldir").open("a") as stream:
            stream.write(f"singleton {name} 1.0 {name}.qml\n")
    (base / "services/qmldir").write_text('singleton AwwwBackend 1.0 AwwwBackend.qml\nsingleton WebWallpaper 1.0 WebWallpaper.qml\n')
    singleton("modules/common", "Config", 'property var options: ({background:{transition:{type:"fade"}}})')
    singleton("modules/common", "Appearance", 'property bool animationsEnabled: true')
    singleton("modules/common", "Directories", f'property string tempPath: "{base}/runtime/inir"')
    singleton("services", "WallpaperListener", '''property bool multiMonitorEnabled: false
property var effectivePerMonitor: ({})
function isGifPath(path) { return path.endsWith(".gif") }
function isVideoPath(path) { return path.endsWith(".mp4") }
function getMonitorName(screen) { return screen.name }
''')
    singleton("modules/common/functions", "FileUtils", 'function trimFileProtocol(path) { return path.replace(/^file:\\/\\//, "") }')
    singleton("modules/common/functions", "StringUtils", 'function shellSingleQuoteEscape(path) { return path }')
    (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
ShellRoot {
 Component.onCompleted: {
  // Even if legacy binaries are present, disabled backends must not stop them.
  AwwwBackend.clientAvailable = true
  AwwwBackend.daemonAvailable = true
  AwwwBackend._probe()
  AwwwBackend._syncNow()
  AwwwBackend.forceSync()
  AwwwBackend.previewImage("/fixture.png")
  AwwwBackend.cancelPreview()
  WebWallpaper.refresh()
 }
 Timer { running: true; interval: 800; onTriggered: {
  if (AwwwBackend.active || AwwwBackend.internalShaderTransitionActive || WebWallpaper.active)
   console.error("FAIL disabled backend active")
  else console.log("PASS disabled legacy backends are inert")
  Qt.quit()
 } }
}''')
    log = base / "process.log"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(base / "runtime"),
               XDG_CONFIG_HOME=str(base / "config"), XDG_CACHE_HOME=str(base / "cache"),
               XDG_STATE_HOME=str(base / "state"), BACKEND_PROCESS_LOG=str(log))
    result = subprocess.run(["qs", "-p", str(base), "--no-color"], env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
    print(result.stdout)
    assert "PASS disabled legacy backends are inert" in result.stdout
    assert "FAIL" not in result.stdout and "ReferenceError" not in result.stdout
    assert not log.exists(), "disabled backend launched a subprocess"
