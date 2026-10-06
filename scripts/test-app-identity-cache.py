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
        (base / 'qmldir').write_text('singleton DesktopEntries 1.0 DesktopEntries.qml\nsingleton AppSearch 1.0 AppSearch.qml\n')
        (base / 'DesktopEntries.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
    property var applications: QtObject { property var values: [] }
    property int lookups: 0
    property int scans: 0
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
''' + cache_property(app, 'desktopLookupCache', '    ') + '\n' + '\n'.join(
            function(app, name, '    ') for name in ['lookupDesktopEntry', '_lookupDesktopEntryUncached']) + '\n}\n')
        (base / 'HintLookup.qml').write_text('''import QtQuick
import "."
QtObject {
    id: root
''' + cache_property(mpris, 'desktopHintCache', '\t') + '\n' + '\n'.join(
            function(mpris, name, '\t') for name in ['_cleanDisplayName', '_volumeKey', '_volumeTokens', '_desktopEntryForHint', '_desktopEntryForHintUncached']) + '\n}\n')
        (base / 'tst_identity.qml').write_text('''import QtQuick
import QtTest
import "."
TestCase {
    name: "DesktopIdentityCache"
    HintLookup { id: hints }
    function init() {
        DesktopEntries.applications.values = []
        DesktopEntries.lookups = 0
        DesktopEntries.scans = 0
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
        const entry = {id: "sample.desktop", name: "Sample", get command() { DesktopEntries.scans++; return ["sample"] }}
        DesktopEntries.applications.values = [entry]
        compare(hints._desktopEntryForHint("unknown-audio-stream"), null)
        const first = DesktopEntries.scans
        verify(first > 0)
        for (let i = 0; i < 20; i++) compare(hints._desktopEntryForHint(" unknown-audio-stream "), null)
        compare(DesktopEntries.scans, first)
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
        return subprocess.run([runner, '-input', temp, '-import', temp], env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
