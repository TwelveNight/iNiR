#!/usr/bin/env python3
"""Exercise bounded startup-only identity warmup and cancellation in Qt 6."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='inir-warmup-test-') as temp:
        base = Path(temp)
        services = base / 'qs/services'
        services.mkdir(parents=True)
        (services / 'qmldir').write_text('module qs.services\nsingleton Audio 1.0 Audio.qml\nsingleton MprisController 1.0 MprisController.qml\n')
        (services / 'Audio.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool ready: false; property var outputAppNodes: [] }')
        (services / 'MprisController.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
    property var icons: []
    property var names: []
    property var times: []
    function streamIconName(node) { icons = icons.concat([node.id]); times = times.concat([Date.now()]); return "audio" }
    function streamDisplayName(node) { names = names.concat([node.id]); return "app" }
}
''')
        (base / 'IrisSidebarWarmup.qml').write_text((ROOT / 'modules/iris/sidebar/IrisSidebarWarmup.qml').read_text())
        (base / 'tst_warmup.qml').write_text('''
import QtQuick
import QtTest
import qs.services
TestCase {
    id: testRoot
    name: "IrisSidebarWarmup"
    property var pauseAfterOne: null
    Connections {
        target: MprisController
        function onIconsChanged() { if (testRoot.pauseAfterOne && MprisController.icons.length===1) testRoot.pauseAfterOne.paused=true }
    }
    Component { id: factory; IrisSidebarWarmup { property bool pauseOnStart: false; onStartedChanged: if (started && pauseOnStart) paused=true } }
    function node(id) { return {id:id,audio:{}} }
    function init() {
        pauseAfterOne = null
        Audio.ready = false
        Audio.outputAppNodes = [node(1),node(2),node(3)]
        MprisController.icons = []; MprisController.names = []; MprisController.times = []
    }
    function test_waits_then_yields_between_nodes_and_stops() {
        const warm = createTemporaryObject(factory, this, {active:true})
        wait(300)
        compare(MprisController.icons.length,0)
        Audio.ready = true
        tryCompare(warm,"complete",true,800)
        compare(MprisController.icons,[1,2,3])
        compare(MprisController.names,[1,2,3])
        const times=MprisController.times
        verify(times[1]-times[0]>=20 && times[2]-times[1]>=20)
        Audio.outputAppNodes = [node(4)]
        wait(150)
        compare(MprisController.icons,[1,2,3],"no permanent hidden stream work")
    }
    function test_pause_and_disable_cancel_pending_work() {
        Audio.ready = true
        const warm = createTemporaryObject(factory,this,{active:true,paused:true})
        wait(300)
        compare(MprisController.icons.length,0)
        testRoot.pauseAfterOne = warm
        warm.paused = false
        tryVerify(() => MprisController.icons.length===1,600)
        warm.paused = true
        wait(100)
        compare(MprisController.icons.length,1)
        warm.active = false
        warm.paused = false
        wait(150)
        compare(MprisController.icons.length,1)
        compare(warm.pending.length,0)
    }
    function test_empty_snapshot_and_disappeared_stream() {
        Audio.ready = true
        Audio.outputAppNodes = []
        const empty = createTemporaryObject(factory,this,{active:true})
        tryCompare(empty,"complete",true,500)
        compare(empty.processed,0)
        Audio.outputAppNodes = [node(7),node(8)]
        const warm = createTemporaryObject(factory,this,{active:true,pauseOnStart:true})
        tryCompare(warm,"started",true,500)
        warm.pending[0] = null
        warm.paused = false
        tryCompare(warm,"complete",true,300)
        compare(MprisController.icons,[8])
        compare(warm.processed,1)
    }
    function test_destroy_cancels_timer() {
        Audio.ready = true
        const warm = factory.createObject(this,{active:true})
        warm.destroy()
        wait(400)
        compare(MprisController.icons.length,0)
    }
}
''')
        result=subprocess.run(['/usr/lib/qt6/bin/qmltestrunner','-input',str(base),'-import',str(base)],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),text=True,capture_output=True)
        output=result.stdout+result.stderr
        print(output,end='')
        if any(error in output for error in ['Binding loop','Invalid context','TypeError','ReferenceError']):
            return 1
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
