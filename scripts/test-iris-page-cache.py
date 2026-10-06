#!/usr/bin/env python3
"""Exercise optional Island/sidebar retention using the production QML policy."""
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
    text = (ROOT / "modules/iris/bar/IrisIsland.qml").read_text()
    page = text.split("                component Page: ColumnLayout {", 1)[1]
    page = "component Page: ColumnLayout {" + page.split("                Item {\n                    id: pageStack", 1)[0]
    composition = (ROOT / "modules/iris/ShellIrisPanelsImpl.qml").read_text()
    loader = composition.split("    component OnDemandPanelLoader: LazyLoader {", 1)[1].split("    IrisAppsSync {}", 1)[0]
    loader = "component OnDemandPanelLoader: Item {\nproperty bool loading\nproperty bool activeAsync\n" + loader
    with tempfile.TemporaryDirectory(prefix="inir-page-test-") as temp:
        base = Path(temp)
        (base / "IrisStyle.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property int feedbackEasing: Easing.OutQuad
    property int morphDuration: 100
    property int revealDuration: 1
    property var morphCurve: [0.2, 0, 0, 1, 1, 1]
    function duration(ms) { return ms }
}
''')
        mocks = {
            "Config": "property bool ready: true; property var options: ({enabledPanels:['test']})",
            "IrisGate": "property bool official: true",
            "GlobalStates": "property bool deferredPanelsReady: true",
        }
        for name, properties in mocks.items():
            (base / (name + ".qml")).write_text("pragma Singleton\nimport QtQuick\nQtObject { " + properties + " }\n")
        (base / "qmldir").write_text("".join("singleton " + name + " 1.0 " + name + ".qml\n" for name in ["IrisStyle", *mocks]))
        (base / "tst_cache.qml").write_text('''
import QtQuick
import QtQuick.Layouts
import QtTest
import "."
TestCase {
    id: root
    name: "IrisIslandPageCache"
    property string effectivePage: "alpha"
    property string pageIntent: ""
    property bool visualExpanded: false
    property bool bottomEdge: false
    property int created: 0
    QtObject { id: details; property bool warm: true; property bool keepLoaded: false; property real opacity: 1 }
''' + page + loader + '''
    OnDemandPanelLoader { id: retained; identifier: "test"; open: false }
    OnDemandPanelLoader { id: disposable; identifier: "test"; open: false }
    function test_sidebar_preloads_only_when_enabled() {
        verify(!retained.activeAsync)
        verify(!disposable.activeAsync)
        retained.keepLoaded = true
        verify(retained.activeAsync)
        retained.open = true
        disposable.open = true
        verify(retained.activeAsync)
        verify(disposable.activeAsync)
        retained.open = false
        disposable.open = false
        wait(100)
        verify(retained.activeAsync)
        verify(!disposable.activeAsync)
        retained.keepLoaded = false
        verify(!retained.activeAsync)
        retained.keepLoaded = true
        verify(retained.activeAsync)
        Config.ready = false
        verify(!retained.activeAsync)
        Config.ready = true
        verify(retained.activeAsync)
        // Reopening before grace expires must cancel the stale release.
        disposable.open = true
        disposable.open = false
        wait(10)
        disposable.open = true
        wait(100)
        verify(disposable.activeAsync)
        disposable.open = false
        wait(100)
        verify(!disposable.activeAsync)
    }
    Page {
        id: alpha
        name: "alpha"
        Loader {
            id: alphaLoader
            active: alpha.resident
            sourceComponent: Item { Component.onCompleted: root.created++ }
        }
    }
    Page {
        id: beta
        name: "beta"
        Loader {
            id: betaLoader
            active: beta.resident
            sourceComponent: Item { Component.onCompleted: root.created++ }
        }
    }
    Page {
        id: unused
        name: "unused"
        Loader { active: unused.resident; sourceComponent: Item { Component.onCompleted: root.created++ } }
    }
    function test_reuse_then_release() {
        compare(created, 1)
        verify(!unused.resident)
        const firstAlpha = alphaLoader.item
        verify(!alpha.enabled, "a retained closed page cannot receive input")
        root.visualExpanded = true
        verify(alpha.enabled)
        root.effectivePage = "beta"
        compare(created, 2)
        verify(!alpha.visible)
        verify(!alpha.enabled, "a cached non-current page cannot receive input")
        verify(alpha.resident)
        root.effectivePage = "alpha"
        compare(created, 2)
        compare(alphaLoader.item, firstAlpha)
        root.visualExpanded = false
        verify(!alpha.enabled)
        verify(!unused.resident)
        details.keepLoaded = true
        details.warm = false
        verify(beta.resident)
        compare(created, 2)
        details.keepLoaded = false
        verify(!beta.resident)
        compare(betaLoader.item, null)
        verify(alpha.resident)
        root.effectivePage = "beta"
        compare(created, 3)
        verify(!alpha.resident)
        compare(alphaLoader.item, null)
    }
}
''')
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_FORCE_STDERR_LOGGING="1")
        return subprocess.run([runner, "-input", str(base), "-import", str(base)], env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
