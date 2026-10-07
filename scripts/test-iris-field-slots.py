#!/usr/bin/env python3
"""Check actual field uniforms, shape invalidation and join map reuse in Qt 6."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='inir-field-test-') as temp:
        base = Path(temp)
        def module(name, component, body):
            directory = base / name.replace('.', '/')
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'qmldir').write_text(f'module {name}\nsingleton {component} 1.0 {component}.qml\n')
            (directory / (component + '.qml')).write_text('pragma Singleton\nimport QtQuick\nQtObject { ' + body + ' }')
        module('qs.modules.common', 'Appearance', 'property bool compositorBlurActive: true')
        module('qs.modules.iris.style', 'IrisStyle', '''
property bool glassCompositor: true; property bool glassWallpaper: false
property real density: 1; property real fuse: 12; property real rimWidth: 1
property color bodySurface: "#333333"; property color rim: "#aaaaaa"; property color glassEdgeColour: "white"; property color shadow: "#55000000"
property real glassEdgeLight: 1; property real glassEdgeLine: 1; property real glassEdgeWidth: 1; property bool edgeLit: true; property real glassTint: 0.1; property real glassLip: 1
''')
        module('qs.modules.iris.frame', 'IrisFrame', '''
property bool framed: false; property real band: 6; property real cornerRadius: 20
property int musicAppearanceCode: 0; property color musicInk: "white"; property real musicLight: 1; property real musicLightWidth: 1
''')
        module('qs.services', 'IrisGlassBackdrops', 'function find(host, fallback) { return null } function register(host, source) {} function unregister(source) {}')
        (base / 'IrisGlassSource.qml').write_text('import QtQuick\nItem { property var screen: null; property bool ready: false; property Item texture: null }')
        source = (ROOT / 'modules/iris/field/IrisField.qml').read_text()
        # Quickshell's plugin is executable-owned. Replace only the attached
        # desktop window access; the actual field, shadows and uniforms run here.
        source = source.replace('import Quickshell\n', '').replace('root.QsWindow.contentItem', 'null').replace('root.QsWindow.window?.screen', 'null')
        (base / 'IrisField.qml').write_text(source)
        (base / 'IrisField.frag.qsb').write_bytes((ROOT / 'modules/iris/field/IrisField.frag.qsb').read_bytes())
        (base / 'tst_field.qml').write_text('''
import QtQuick
import QtTest
import qs.modules.iris.style
TestCase {
    name: "IrisFieldSlots"
    when: windowShown
    IrisField { id: field; width: 400; height: 300; compositorAllowed: true }
    function shader() { return field.children.find(child => child.shape0 !== undefined) }
    function body(overrides) { return Object.assign({id:"one",x:20,y:30,width:40,height:60,radius:9,joins:["frame"],glass:"compositor",fuse:5,paints:true}, overrides ?? {}) }
    function init() { field.shapes = []; field.framed = false; IrisStyle.fuse = 12 }
    function test_isolated_updates_and_uniforms() {
        field.shapes = [body(), body({id:"two",x:100,joins:["one"]})]
        const second = field.shapeSlots[1].shape
        const map = shader().indexOf
        compare(shader().shape0, Qt.vector4d(40,60,20,30))
        compare(shader().shape1, Qt.vector4d(120,60,20,30))
        compare(shader().radiiA.x, 9)
        compare(shader().fuseA.x, 5)
        compare(shader().paintsA.x, 1)
        compare(shader().glassA.x, 2)
        compare(shader().joinA.y, 1)
        field.shapes = [body({x:25}), body({id:"two",x:100,joins:["one"]})]
        compare(field.shapeSlots[1].shape, second)
        compare(shader().indexOf, map)
        compare(shader().shape0.x, 45)
        field.framed = true
        compare(shader().joinA.x, -1)
        field.shapes = [body({x:25, id:"renamed",glass:"solid",radius:15,paints:false,joins:["two"]}), body({id:"two",x:100,joins:["one"]})]
        compare(shader().radiiA.x, 15)
        compare(shader().paintsA.x, 0)
        compare(shader().glassA.x, 0)
        compare(shader().joinA.x, 2)
        compare(shader().joinA.y, 0)
        verify(shader().indexOf !== map)
    }
    function test_removal_empty_slots_and_style_changes() {
        field.shapes = [body({fuse:undefined,glass:"inherit"}), body({id:"two"})]
        IrisStyle.fuse = 24
        compare(shader().fuseA.x, 24)
        field.compositorAllowed = false
        compare(shader().glassA.x, 1)
        field.compositorAllowed = true
        compare(shader().glassA.x, 2)
        field.shapes = [body()]
        compare(field.shapeSlots[1].shape, null)
        compare(shader().shape1, Qt.vector4d(0,0,0,0))
        compare(shader().radiiA.y, 0)
        compare(shader().joinA.y, 0)
        field.shapes = []
        compare(shader().shape0, Qt.vector4d(0,0,0,0))
        compare(shader().shape19, Qt.vector4d(0,0,0,0))
        compare(field.bounds.width, 0)
    }
    function test_capacity_and_equal_joins() {
        const list = Array.from({length:25}, (_,i) => body({id:String(i),x:i*3,joins:[]}))
        field.shapes = list
        compare(field.shapeSlots.length, 20)
        compare(shader().shape19.x, 77)
        const last = field.shapeSlots[19].shape
        field.shapes = list.map(item => Object.assign({}, item, {joins:[]}))
        compare(field.shapeSlots[19].shape, last)
        field.shapes = [body({joins:["one","frame"]})]
        compare(shader().alsoA.x, 0)
        field.framed = true
        compare(shader().alsoA.x, -1)
    }
}
''')
        result = subprocess.run(['/usr/lib/qt6/bin/qmltestrunner', '-input', str(base), '-import', str(base)], env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software'), text=True, capture_output=True)
        print(result.stdout + result.stderr, end='')
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
