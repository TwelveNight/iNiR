#!/usr/bin/env python3
"""Exercise output-refresh signals and real monitor snapshot functions offscreen."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MonitorRefreshTests(unittest.TestCase):
    def test_native_screen_signals_refresh_without_polling_or_other_compositor(self):
        source = (ROOT / 'services/NiriService.qml').read_text()
        hooks = source.split('    property var outputs: ({})', 1)[1].split('    property var windows:', 1)[0]
        hooks = hooks.replace('Quickshell.screens', 'screenRegistry.screens').replace(
            'target: Quickshell', 'target: screenRegistry').replace('CompositorService.isNiri', 'root.isNiri')
        qml = '''import QtQuick
import QtTest
Item {
    id: root
    property bool isNiri: true
    property int requests: 0
    function fetchOutputs() { if (isNiri) requests++ }
    QtObject { id: screenRegistry; property var screens: [firstScreen] }
    QtObject { id: firstScreen; property rect geometry: Qt.rect(0, 0, 2560, 1440); signal physicalPixelDensityChanged() }
    QtObject { id: secondScreen; property rect geometry: Qt.rect(2560, 0, 2048, 1280); signal physicalPixelDensityChanged() }
''' + hooks + '''
    TestCase {
        name: "OutputRefresh"
        when: windowShown
        function test_refresh() {
            wait(1)
            const before = root.requests
            screenRegistry.screens = [firstScreen, secondScreen]
            tryVerify(() => root.requests > before)
            wait(1)
            const geometryBefore = root.requests
            secondScreen.geometry = Qt.rect(2560, 100, 2048, 1280)
            compare(root.requests, geometryBefore + 1)
            secondScreen.physicalPixelDensityChanged()
            compare(root.requests, geometryBefore + 2)
            root.isNiri = false
            const otherDesktop = root.requests
            firstScreen.geometry = Qt.rect(0, 10, 2560, 1440)
            screenRegistry.screens = [firstScreen]
            compare(root.requests, otherDesktop)
        }
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='inir-screen-signals-') as directory:
            (Path(directory) / 'tst_outputs.qml').write_text(qml)
            result = subprocess.run(['/usr/lib/qt6/bin/qmltestrunner', '-input', directory, '-platform', 'offscreen'],
                                    env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_snapshot_refreshes_dual_screen_and_keeps_drag_transaction(self):
        source = (ROOT / 'modules/settings/MonitorVisibilityConfig.qml').read_text()
        names = ['niriOutputNames', 'niriLogicalRect', 'boundsForLayout', 'syncMonitorLayoutSnapshot']
        functions = '\n'.join(re.search(r'^    function ' + name + r'\(.*?^    \}', source, re.M | re.S)[0]
                              for name in names)
        functions = re.sub(r':\s*(?:string|var|bool|void)\b', '', functions)
        script = '''const assert = require('node:assert/strict');
const NiriService = {outputs: {
    'HDMI-A-1': {logical: {x:-548,y:9,width:2560,height:1440}},
    'eDP-2': {logical:null}
}};
const root = {draggingLayoutOutput:'',monitorLayoutBusy:false,monitorLayoutSnapshot:{},
    monitorLayoutViewportBounds:{},monitorLayoutPreserveViewport:false};
with(root) {
''' + functions + '''
Object.assign(root, {boundsForLayout});
assert.deepEqual(niriOutputNames(), ['HDMI-A-1']);
syncMonitorLayoutSnapshot(false);
assert.deepEqual(niriOutputNames(), ['HDMI-A-1']);
NiriService.outputs['eDP-2'].logical = {x:2012,y:337,width:2048,height:1280};
syncMonitorLayoutSnapshot(false);
assert.deepEqual(niriOutputNames(), ['HDMI-A-1','eDP-2']);
assert.equal(root.monitorLayoutViewportBounds.width, 4608);
assert.equal(root.monitorLayoutViewportBounds.height, 1608);
assert.equal(niriLogicalRect('eDP-2').width, 2048);
root.draggingLayoutOutput = 'eDP-2';
NiriService.outputs['eDP-2'].logical.x = 2100;
syncMonitorLayoutSnapshot(false);
assert.equal(niriLogicalRect('eDP-2').x, 2012);
root.draggingLayoutOutput = '';
root.monitorLayoutBusy = true;
syncMonitorLayoutSnapshot(false);
assert.equal(niriLogicalRect('eDP-2').x, 2012);
root.monitorLayoutBusy = false;
syncMonitorLayoutSnapshot(false);
assert.equal(niriLogicalRect('eDP-2').x, 2100);
}
'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
