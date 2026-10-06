#!/usr/bin/env python3
"""Execute production input policies during close, reversal and retained idle.

This isolates policy from rendering; live Wayland mapping and mouse delivery
must also be checked when deploying panel lifetime changes.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def binding(source, name):
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(name + ":"))
    value = lines[start].split(":", 1)[1].strip()
    for line in lines[start + 1:]:
        if not line.lstrip().startswith(("?", ":", "||", "&&")):
            break
        value += "\n" + line.strip()
    return value


def main():
    runner = "/usr/lib/qt6/bin/qmltestrunner"
    if not Path(runner).is_file():
        runner = shutil.which("qmltestrunner6")
    if not runner:
        raise SystemExit("Qt 6 qmltestrunner is required")
    sidebar = (ROOT / "modules/iris/sidebar/IrisSidebar.qml").read_text()
    bar = (ROOT / "modules/iris/bar/IrisBar.qml").read_text()
    qml = '''
import QtQuick
import QtTest
TestCase {
    id: root
    name: "IrisInputLifetime"
    property bool open: false
    property bool pinned: false
    property bool peek: false
    QtObject { id: frame; property real progress: 0 }
    QtObject { id: ownMask }
    QtObject { id: emptyMask }
    QtObject { id: emptyRegion }
    QtObject { id: chassisRegion }
    property var focusModes: ({None: 0, OnDemand: 1, Exclusive: 2})
    readonly property bool mapped: SIDEBAR_VISIBLE
    readonly property var inputMask: SIDEBAR_MASK
    readonly property int keyboard: SIDEBAR_KEYBOARD
    QtObject { id: barWindow; property bool expanded: false; property bool pinned: false; property bool canvasSuppressed: false }
    QtObject { id: stage; property bool cardArmed: false }
    QtObject { id: controlCentreLoader; property var item: null }
    QtObject { id: dockLoader; property var item: null }
    QtObject { id: spotlightLoader; property var item: null }
    QtObject { id: galleryLoader; property var item: null }
    QtObject { id: orbitLoader; property var item: null }
    QtObject { id: islandLoader; property var item: ({morphing: false}) }
    readonly property var barMask: BAR_MASK
    function test_sidebar_close_and_reverse() {
        compare(inputMask, emptyMask)
        verify(!mapped)
        compare(keyboard, WlrKeyboardFocus.None)
        root.open = true
        frame.progress = 0.6
        verify(mapped)
        compare(inputMask, ownMask)
        compare(keyboard, WlrKeyboardFocus.Exclusive)
        root.open = false
        verify(mapped, "closing animation still draws")
        compare(inputMask, emptyMask, "closing immediately releases pointer input")
        compare(keyboard, WlrKeyboardFocus.None)
        root.open = true
        compare(inputMask, ownMask)
        root.pinned = true
        compare(keyboard, WlrKeyboardFocus.OnDemand)
        root.open = false
        compare(keyboard, WlrKeyboardFocus.None)
        compare(inputMask, emptyMask)
        frame.progress = 0
        verify(!mapped, "cached idle panel unmaps")
    }
    function test_island_close_does_not_capture_full_output() {
        compare(barMask, chassisRegion)
        barWindow.expanded = true
        islandLoader.item = {morphing: true}
        compare(barMask, null)
        barWindow.expanded = false
        compare(barMask, chassisRegion, "close releases full-output capture before morph finishes")
        stage.cardArmed = true
        compare(barMask, null, "an actually open card still owns dismissal input")
        barWindow.canvasSuppressed = true
        compare(barMask, emptyRegion)
        stage.cardArmed = false
        barWindow.canvasSuppressed = false
        islandLoader.item = {morphing: false}
        compare(barMask, chassisRegion)
    }
}
'''
    for key, value in {
        "SIDEBAR_VISIBLE": binding(sidebar, "visible"),
        "SIDEBAR_MASK": binding(sidebar, "mask"),
        "SIDEBAR_KEYBOARD": binding(sidebar, "WlrLayershell.keyboardFocus"),
        "BAR_MASK": binding(bar, "mask"),
    }.items():
        qml = qml.replace(key, value)
    qml = qml.replace("WlrKeyboardFocus.", "focusModes.")
    with tempfile.TemporaryDirectory(prefix="inir-input-test-") as temp:
        Path(temp, "tst_input.qml").write_text(qml)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        return subprocess.run([runner, "-input", temp], env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
