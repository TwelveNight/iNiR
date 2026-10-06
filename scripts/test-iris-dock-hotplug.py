#!/usr/bin/env python3
"""Exercise iRiS Dock lifetimes against the real sorting service offscreen."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "modules/iris/dock/IrisDock.qml").read_text()
lifecycle = "\n".join(re.findall(
    r"^    Component\.on(?:Completed|Destruction):[^\n]+", source, re.MULTILINE))
assert len(lifecycle.splitlines()) == 2

with tempfile.TemporaryDirectory(prefix="inir-iris-dock-hotplug-") as directory:
    base = Path(directory)
    services = base / "services"
    services.mkdir()
    (services / "qmldir").write_text(
        "singleton CompositorService 1.0 CompositorService.qml\n"
        "singleton NiriService 1.0 NiriService.qml\n")
    shutil.copyfile(ROOT / "services/CompositorService.qml", services / "CompositorService.qml")
    (services / "NiriService.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property var activeWindow: null
    signal windowOrderChanged
    function sortToplevels(handles) { return [{appId: "firefox", niriWindowId: 1}] }
}
''')
    (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
Scope {
    id: testRoot
    property var externalDock: null
    property var internalDock: null
    property int step: 0
    function check(value, message) { if (!value) throw new Error(message) }
    Component {
        id: dock
        Item {
''' + lifecycle + '''
        }
    }
    Timer {
        interval: 180
        running: true
        repeat: true
        onTriggered: {
            try {
                if (testRoot.step === 0) {
                    testRoot.externalDock = dock.createObject(testRoot)
                    testRoot.internalDock = dock.createObject(testRoot)
                } else if (testRoot.step === 1) {
                    check(CompositorService.sortingActive, "Two Docks must demand sorting")
                    check(CompositorService.sortedToplevels.length === 1, "Running app missing initially")
                    testRoot.internalDock.destroy()
                } else if (testRoot.step === 2) {
                    check(CompositorService.sortingActive, "Removing internal Dock disabled the external Dock")
                    check(CompositorService.sortedToplevels.length === 1, "Lid close removed running apps")
                    testRoot.internalDock = dock.createObject(testRoot)
                } else if (testRoot.step === 3) {
                    check(CompositorService.sortingActive, "Lid open did not restore demand")
                    testRoot.externalDock.destroy()
                } else if (testRoot.step === 4) {
                    check(CompositorService.sortingActive, "External disconnect disabled internal Dock")
                    check(CompositorService.sortedToplevels.length === 1, "External disconnect removed running apps")
                    testRoot.internalDock.destroy()
                } else {
                    check(!CompositorService.sortingActive, "Last Dock did not release sorting")
                    check(CompositorService.sortedToplevels.length === 0, "Inactive sorting retained its cache")
                    console.log("IRIS_DOCK_HOTPLUG_PASS")
                    Qt.quit()
                }
                testRoot.step++
            } catch (e) {
                console.error("IRIS_DOCK_HOTPLUG_FAIL", e)
                Qt.quit()
            }
        }
    }
}
''')
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QSG_RHI_BACKEND="software",
               NIRI_SOCKET="/tmp/inir-test-niri.sock", HYPRLAND_INSTANCE_SIGNATURE="")
    result = subprocess.run(["qs", "-p", str(base), "--no-color"], env=env,
                            capture_output=True, text=True, timeout=15)
    log = result.stdout + result.stderr
    if "IRIS_DOCK_HOTPLUG_PASS" not in log or "IRIS_DOCK_HOTPLUG_FAIL" in log:
        raise SystemExit(log)
    print("PASS iRiS Dock: lid close/open, external disconnect, final sorting release")
