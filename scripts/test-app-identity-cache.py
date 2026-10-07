#!/usr/bin/env python3
"""Qt regression tests for bounded positive/negative desktop identity caching."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, name, indent):
    start = source.index(indent + 'function ' + name + '(')
    end = source.index('\n' + indent + '}', start) + len(indent) + 2
    return source[start:end]


def cache_property(source, name, indent):
    start = source.index(indent + 'readonly property var ' + name + ': {')
    end = source.index('\n' + indent + '}', start) + len(indent) + 2
    return source[start:end]


def main():
    runner = '/usr/lib/qt6/bin/qmltestrunner'
    if not Path(runner).is_file():
        runner = shutil.which('qmltestrunner6')
    if not runner:
        raise SystemExit('Qt 6 qmltestrunner is required')
    app = (ROOT / 'services/AppSearch.qml').read_text()
    mpris = (ROOT / 'services/MprisController.qml').read_text()
    with tempfile.TemporaryDirectory(prefix='inir-identity-test-') as temp:
        base = Path(temp)
        (base / 'qmldir').write_text('singleton DesktopEntries 1.0 DesktopEntries.qml\nsingleton AppSearch 1.0 AppSearch.qml\n' + ''.join('singleton ' + name + ' 1.0 ' + name + '.qml\n' for name in ['Config','Appearance','IconThemeService','Quickshell']))
        for name, properties in {
            'Config': 'property var options: ({appearance:{iconTheme:"default"}})',
            'Appearance': 'property var m3colors: ({darkmode:true})',
            'IconThemeService': 'property string currentTheme: "default"',
            'Quickshell': 'property int probes: 0; property var available: ({known:true}); function iconPath(name, fallback) { probes++; return available[name] ? "file:///" + name : "" }',
        }.items():
            (base / (name + '.qml')).write_text('pragma Singleton\nimport QtQuick\nQtObject { ' + properties + ' }')
        (base / 'DesktopEntries.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
    property var applications: QtObject { property var values: [] }
    property int lookups: 0
    readonly property var counters: ({scans:0})
    function heuristicLookup(id) { lookups++; return null }
}
''')
        (base / 'AppSearch.qml').write_text('''pragma Singleton
import QtQuick
import "."
QtObject {
    id: root
    property var _startupClassMap: ({})
    property var _execBasenameMap: ({})
    property var _desktopIdStemMap: ({})
''' + cache_property(app, 'desktopLookupCache', '    ') + '\n' + cache_property(app, 'iconExistsCache', '    ') + '\n' + '\n'.join(
            function(app, name, '    ') for name in ['lookupDesktopEntry', '_lookupDesktopEntryUncached', 'iconExists']) + '\n}\n')
        (base / 'HintLookup.qml').write_text('''import QtQuick
import "."
QtObject {
    id: root
''' + cache_property(mpris, 'desktopHintCache', '\t') + '\n' + cache_property(mpris, 'desktopHintIndex', '\t') + '\n' + '\n'.join(
            function(mpris, name, '\t') for name in ['_cleanDisplayName', '_volumeKey', '_volumeTokens', '_desktopEntryForHint', '_desktopEntryForHintUncached']) + '\n}\n')
        (base / 'tst_identity.qml').write_text('''import QtQuick
import QtTest
import "."
TestCase {
    name: "DesktopIdentityCache"
    HintLookup { id: hints }
    function init() {
        DesktopEntries.applications.values = []
        Quickshell.probes = 0
        Quickshell.available = {known:true}
        DesktopEntries.lookups = 0
        DesktopEntries.counters.scans = 0
        AppSearch._startupClassMap = {}
        AppSearch._execBasenameMap = {}
        AppSearch._desktopIdStemMap = {}
    }
    function test_negative_results_are_cached() {
        compare(AppSearch.lookupDesktopEntry("unknown-audio-stream"), null)
        const first = DesktopEntries.lookups
        for (let i = 0; i < 20; i++) compare(AppSearch.lookupDesktopEntry("unknown-audio-stream"), null)
        compare(DesktopEntries.lookups, first)
    }
    function test_positive_result_and_index_rebuild() {
        const entry = {id: "sample.desktop", name: "Sample"}
        AppSearch._desktopIdStemMap = {sample: entry}
        compare(AppSearch.lookupDesktopEntry("sample"), entry)
        const first = DesktopEntries.lookups
        compare(AppSearch.lookupDesktopEntry("sample"), entry)
        compare(DesktopEntries.lookups, first)
        AppSearch._desktopIdStemMap = {}
        compare(AppSearch.lookupDesktopEntry("sample"), null)
    }
    function test_new_entries_invalidate_misses() {
        compare(hints._desktopEntryForHint("Music Player"), null)
        const entry = {id: "music.desktop", name: "Music Player", command: ["music"]}
        DesktopEntries.applications.values = [entry]
        compare(hints._desktopEntryForHint("Music Player"), entry)
        DesktopEntries.applications.values = []
        compare(hints._desktopEntryForHint("Music Player"), null)
    }
    function test_mpris_does_not_rescan_for_repeated_unknown_hint() {
        const entry = {id: "sample.desktop", name: "Sample", get command() { DesktopEntries.counters.scans++; return ["sample"] }}
        DesktopEntries.applications.values = [entry]
        compare(hints._desktopEntryForHint("unknown-audio-stream"), null)
        const first = DesktopEntries.counters.scans
        verify(first > 0)
        for (let i = 0; i < 20; i++) compare(hints._desktopEntryForHint(" unknown-audio-stream "), null)
        compare(DesktopEntries.counters.scans, first)
    }
    function test_distinct_hints_reuse_normalized_metadata() {
        const entry = {id:"music.desktop", name:"Music Player", get command() { DesktopEntries.counters.scans++; return ["music"] }}
        DesktopEntries.applications.values = [entry]
        compare(hints._desktopEntryForHint("Music Player"), entry)
        const scans = DesktopEntries.counters.scans
        compare(hints._desktopEntryForHint("Music Player audio"), entry)
        compare(hints._desktopEntryForHint("unrelated stream"), null)
        compare(DesktopEntries.counters.scans, scans)
        DesktopEntries.applications.values = [{id:"hidden.desktop",name:"Music Player",noDisplay:true}]
        compare(hints._desktopEntryForHint("Music Player"), null)
    }
    function test_icon_hits_and_misses_are_bounded_and_invalidated() {
        verify(AppSearch.iconExists("known"))
        verify(!AppSearch.iconExists("missing"))
        const probes = Quickshell.probes
        for (let i=0;i<10;i++) {
            verify(AppSearch.iconExists("known"))
            verify(!AppSearch.iconExists("missing"))
        }
        verify(!AppSearch.iconExists("image-missing"))
        compare(Quickshell.probes, probes)
        Quickshell.available = {known:true,missing:true}
        Config.options = {appearance:{iconTheme:"new"}}
        verify(AppSearch.iconExists("missing"))
        Quickshell.available = {}
        IconThemeService.currentTheme = "external"
        verify(!AppSearch.iconExists("known"))
        Quickshell.available = {known:true}
        Appearance.m3colors = {darkmode:false}
        verify(AppSearch.iconExists("known"))
        Quickshell.available = {}
        DesktopEntries.applications.values = [{id:"new.desktop"}]
        verify(!AppSearch.iconExists("known"))
        for (let i=0;i<300;i++) AppSearch.iconExists("absent"+i)
        compare(AppSearch.iconExistsCache.size,256)
        verify(!AppSearch.iconExistsCache.has("absent0"))
        verify(AppSearch.iconExistsCache.has("absent299"))
    }
    function test_cache_bound_and_eviction() {
        for (let i = 0; i < 300; i++) hints._desktopEntryForHint("missing" + i)
        compare(AppSearch.desktopLookupCache.size, 256)
        compare(hints.desktopHintCache.size, 256)
        verify(!hints.desktopHintCache.has("missing0"))
        verify(hints.desktopHintCache.has("missing299"))
    }
}
''')
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
        result = subprocess.run([runner, '-input', temp, '-import', temp], env=env, text=True, capture_output=True)
        output = result.stdout + result.stderr
        print(output, end='')
        if any(error in output for error in ['Binding loop', 'Invalid context', 'TypeError', 'ReferenceError']):
            return 1
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
