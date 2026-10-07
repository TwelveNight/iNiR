#!/usr/bin/env python3
"""Exercise async icon fallback and source changes in the actual QML component."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="inir-icon-test-") as temp:
        base = Path(temp)
        for name, contents in {
            "qs.services": {"AppSearch": 'pragma Singleton\nimport QtQml\nQtObject { function resolveIcon(icon, fallback) { return icon || fallback } }'},
            "qs.modules.common": {"Appearance": 'pragma Singleton\nimport QtQml\nQtObject { property var colors: ({colOnLayer1:"white"}) }', "Directories": 'pragma Singleton\nimport QtQml\nQtObject { property string assetsPath: "" }'},
        }.items():
            directory = base / name.replace('.', '/')
            directory.mkdir(parents=True)
            (directory / 'qmldir').write_text('module ' + name + '\n' + ''.join('singleton ' + key + ' 1.0 ' + key + '.qml\n' for key in contents))
            for key, content in contents.items():
                (directory / (key + '.qml')).write_text(content)
        # Image, Loader, Timer and Kirigami.Icon are the real Qt/KDE implementations.
        (base / 'SmartAppIcon.qml').write_text((ROOT / 'modules/common/widgets/SmartAppIcon.qml').read_text())
        (base / 'valid.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="red"/></svg>')
        (base / 'tst_icon.qml').write_text('''
import QtQuick
import QtTest
TestCase {
    name: "SmartAppIconLifecycle"
    when: windowShown
    Component { id: factory; SmartAppIcon { color: "white" } }
    function loader(icon) { return icon.children.find(child => child.item !== undefined) }
    function test_missing_cached_and_source_recovery() {
        for (let n = 0; n < 3; n++) {
            const icon = createTemporaryObject(factory, this, {icon: Qt.resolvedUrl("missing.png").toString()})
            verify(icon)
            tryCompare(icon, "_imageError", true)
            compare(loader(icon).item.source.toString(), icon.fallback)
            icon.icon = Qt.resolvedUrl("valid.svg").toString()
            tryVerify(() => loader(icon).item.status === Image.Ready)
            compare(icon._imageError, false)
            compare(loader(icon).item.asynchronous, true)
            icon.icon = "folder"
            tryVerify(() => loader(icon).item.source.toString() === "folder")
            compare(icon._imageError, false)
            icon.destroy()
            wait(0)
        }
    }
    function test_obsolete_error_and_destruction() {
        const icon = createTemporaryObject(factory, this, {icon: Qt.resolvedUrl("missing.png").toString()})
        icon.icon = Qt.resolvedUrl("valid.svg").toString()
        tryVerify(() => loader(icon).item.status === Image.Ready)
        wait(30)
        compare(icon._imageError, false)
        for (let n = 0; n < 10; n++) {
            const transient = factory.createObject(this, {icon: Qt.resolvedUrl("missing.png").toString()})
            transient.destroy()
        }
        wait(30)
    }
}
''')
        result = subprocess.run(['/usr/lib/qt6/bin/qmltestrunner', '-input', str(base), '-import', str(base)], env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software'), text=True, capture_output=True)
        print(result.stdout + result.stderr, end='')
        if 'Binding loop' in result.stdout + result.stderr or 'Invalid context' in result.stdout + result.stderr:
            return 1
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
