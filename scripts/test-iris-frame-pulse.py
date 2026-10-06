#!/usr/bin/env python3
"""Exercise music-frame timing and blur publication without a desktop session."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    runner = "/usr/lib/qt6/bin/qmltestrunner"
    if not Path(runner).is_file():
        runner = shutil.which("qmltestrunner6") or shutil.which("qmltestrunner")
    if not runner:
        raise SystemExit("Qt 6 qmltestrunner is required")
    with tempfile.TemporaryDirectory(prefix="inir-pulse-test-") as temp:
        base = Path(temp)

        def module(name, files, singletons=()):
            directory = base / name.replace(".", "/")
            directory.mkdir(parents=True, exist_ok=True)
            entries = ["module " + name]
            for component, content in files.items():
                (directory / (component + ".qml")).write_text(content)
                entries.append(("singleton " if component in singletons else "")
                               + component + " 1.0 " + component + ".qml")
            (directory / "qmldir").write_text("\n".join(entries) + "\n")

        module("qs.services", {
            "MprisController": "pragma Singleton\nimport QtQml\nQtObject { property var activePlayer: ({isPlaying:true}) }",
            "TestAudio": "pragma Singleton\nimport QtQml\nQtObject { property bool audible: false; property var points: [25,25,25,25] }",
        }, ("MprisController", "TestAudio"))
        module("qs.modules.common", {"Config": "pragma Singleton\nimport QtQml\nQtObject { property var options: ({appearance:{cava:{framerate:60}}}) }"}, ("Config",))
        module("qs.modules.iris.style", {"IrisStyle": "pragma Singleton\nimport QtQml\nQtObject { readonly property real density: 1 }"}, ("IrisStyle",))
        module("qs.modules.common.widgets", {"CavaProcess": """
import QtQuick
import qs.services
Item {
    property bool active: false
    property int sampleCount: 0
    readonly property bool held: active
    readonly property bool audioSignalActive: TestAudio.audible
    readonly property var points: TestAudio.points
    readonly property real normalizationCeiling: 100
}
"""})
        module("qs.modules.iris.frame", {"IrisFramePulse": (ROOT / "modules/iris/frame/IrisFramePulse.qml").read_text()})
        blur = (ROOT / "modules/iris/field/IrisWaveBlur.qml").read_text()
        publish = blur[blur.index("        function publish(runs:"):blur.index("        Component.onDestruction: strip.BackgroundEffect")]
        # Execute the production publisher against counted surface/region mocks.
        # This tests redundant commits and stale geometry without a Wayland session.
        (base / "tst_blur.qml").write_text('''
import QtQuick
import QtTest
TestCase {
    id: root
    name: "IrisWaveBlurPublication"
    property int windowWidth: 200
    property int windowHeight: 100
    property int depth: 20
    property int commits: 0
    QtObject { id: effect; property var blurRegion: null }
    QtObject { id: stripRegion; property var regions: [] }
    QtObject {
        id: strip
        property string edge: "right"
        property bool published: false
        property var lastRuns: null
        property int lastOriginX: 0
        property int lastOriginY: 0
        property var pool: []
        property var backgroundEffect: effect
        property var runComponent: ({createObject: () => ({x:0,y:0,width:0,height:0})})
        property var contentItem: ({Window:{window:{update: () => root.commits++}}})
'''
            + publish.replace('strip.BackgroundEffect', 'strip.backgroundEffect') + '''
    }
    function test_publish_deduplicates_but_preserves_updates_and_clear() {
        const rect = {x:182,y:10,width:3,height:5}
        strip.publish([rect])
        compare(commits, 1)
        compare(strip.pool[0].x, 2)
        compare(effect.blurRegion, stripRegion)
        strip.publish([{x:182,y:10,width:3,height:5}])
        compare(commits, 1)
        strip.publish([{x:183,y:10,width:3,height:5}])
        compare(commits, 2)
        compare(strip.pool[0].x, 3)
        root.windowWidth = 202
        strip.publish([{x:183,y:10,width:3,height:5}])
        compare(commits, 3)
        compare(strip.pool[0].x, 1)
        strip.publish([])
        compare(commits, 4)
        compare(effect.blurRegion, null)
        compare(strip.pool[0].width, 0)
        strip.publish([])
        compare(commits, 4)
        strip.publish([rect])
        compare(commits, 5)
        compare(strip.pool.length, 1)
        compare(effect.blurRegion, stripRegion)
    }
}
''')
        (base / "tst_pulse.qml").write_text("""
import QtQuick
import QtTest
import qs.services
import qs.modules.common
import qs.modules.iris.frame
TestCase {
    name: "IrisFramePulse"
    property int updates: 0
    IrisFramePulse { id: pulse; onPhaseChanged: updates++ }
    function init() {
        pulse.active = false
        TestAudio.audible = false
        Config.options = {appearance:{cava:{framerate:60}}}
        updates = 0
    }
    function test_playing_but_silent_is_idle() {
        pulse.active = true
        wait(150)
        compare(updates, 0)
        compare(pulse.level, 0)
    }
    function test_audio_is_capped_and_silence_settles() {
        Config.options = {appearance:{cava:{framerate:240}}}
        compare(pulse.updateFps, 60)
        pulse.active = true
        TestAudio.audible = true
        wait(300)
        verify(pulse.level > 0)
        verify(updates > 2 && updates <= 20, "60 Hz cap: " + updates)
        TestAudio.audible = false
        tryCompare(pulse, "level", 0, 3500)
        const stopped = updates
        wait(150)
        compare(updates, stopped)
        TestAudio.audible = true
        tryVerify(() => pulse.level > 0, 300)
    }
    function test_disable_resets_and_lower_source_rate_is_honoured() {
        Config.options = {appearance:{cava:{framerate:30}}}
        compare(pulse.updateFps, 30)
        pulse.active = true
        TestAudio.audible = true
        wait(300)
        verify(updates > 1 && updates <= 11)
        pulse.active = false
        compare(pulse.level, 0)
        compare(pulse.phase, 0)
        const stopped = updates
        wait(100)
        compare(updates, stopped)
    }
}
""")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_FORCE_STDERR_LOGGING="1")
        return subprocess.run([runner, "-input", str(base), "-import", str(base)], env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
