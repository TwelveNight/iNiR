#!/usr/bin/env python3
"""Exercise production morph arming and warm-frame gates in Qt's event loop."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / 'modules/iris/components/IrisMorphSurface.qml').read_text()
    warm = source[source.index('    property bool armed:'):source.index('    readonly property alias presentation:')]
    warm = warm.replace('target: root.Window.window', 'target: root.frameSource')
    arm = source[source.index('    readonly property bool canArm:'):source.index('    function lerp(a:')]
    with tempfile.TemporaryDirectory(prefix='inir-launch-test-') as temp:
        base = Path(temp)
        (base / 'qmldir').write_text('singleton IrisMotionMeter 1.0 IrisMotionMeter.qml\n')
        (base / 'IrisMotionMeter.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { function watching(surface) { return false } function mark(stage) {} }')
        (base / 'Launch.qml').write_text('''
import QtQuick
import "."
Item {
    id: root
    property bool open: false
    property bool contentReady: true
    property real presentation: 0
    property bool settles: false
    property bool fromIsland: false
    property string originOwner: ""
    property string motionSurface: "panels"
    property int captures: 0
    property QtObject frameSource: QtObject { signal frameSwapped() }
    function captureOrigin() { root.captures++ }
''' + warm + arm + '\n}\n')
        (base / 'tst_launch.qml').write_text('''
import QtQuick
import QtTest
TestCase {
    name: "IrisLaunchReadiness"
    when: windowShown
    Component { id: factory; Launch { width: 400; height: 500 } }
    function make(properties) { return createTemporaryObject(factory, this, properties ?? {}) }
    function test_ready_arms_without_animation_timer_tick() {
        const item = make()
        item.open = true
        // No wait/event processing: the old interval-0 Timer fails here.
        compare(item.armed, true)
        compare(item.activationCount, 1)
        compare(item.captures, 1)
        compare(item.launched, false)
        compare(item.warming, true)
        item.frameSource.frameSwapped()
        compare(item.launched, true)
        compare(item.warming, false)
    }
    function test_waits_for_content_and_nonzero_geometry() {
        const item = make({contentReady:false, width:0, height:0})
        item.open = true
        verify(!item.armed)
        item.contentReady = true
        verify(!item.armed)
        item.width = 400
        verify(!item.armed)
        item.height = 500
        verify(item.armed)
        compare(item.captures, 1)
        verify(!item.launched)
    }
    function test_close_before_first_frame_cancels_launch() {
        const item = make()
        item.open = true
        item.open = false
        verify(!item.armed)
        item.frameSource.frameSwapped()
        wait(120)
        verify(!item.launched)
        item.open = true
        verify(item.armed)
        compare(item.captures, 2)
        compare(item.activationCount, 2)
        item.frameSource.frameSwapped()
        verify(item.launched)
    }
    function test_reversal_preserves_running_motion() {
        const item = make()
        item.open = true
        item.frameSource.frameSwapped()
        item.presentation = 0.5
        item.open = false
        verify(!item.armed)
        item.open = true
        verify(item.armed)
        verify(item.launched)
        compare(item.captures, 1)
    }
    function test_no_frame_fallback_and_disposal() {
        const item = make()
        item.open = true
        tryCompare(item, "launched", true, 250)
        const transient = factory.createObject(this)
        transient.open = true
        transient.destroy()
        wait(120)
    }
}
''')
        result = subprocess.run(['/usr/lib/qt6/bin/qmltestrunner','-input',str(base)], env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'), text=True,capture_output=True)
        output=result.stdout+result.stderr
        print(output,end='')
        if any(error in output for error in ['Binding loop','Invalid context','TypeError','ReferenceError']):
            return 1
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
