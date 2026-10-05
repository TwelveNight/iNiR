pragma Singleton
pragma ComponentBehavior: Bound

import qs
import qs.modules.common
import qs.modules.common.functions
import Quickshell;
import Quickshell.Io;
import QtQuick;
import qs.services

/**
 * For storing sensitive data in the keyring.
 * Use this for small data only, since it stores a JSON of the contents directly and doesn't use a database.
 */
Singleton {
    id: root

    property bool loaded: false
    property var keyringData: ({})
    
    property var properties: {
        "application": "illogical-impulse",
        "explanation": Translation.tr("For storing API keys and other sensitive information"),
    }
    property var propertiesAsArgs: Object.keys(root.properties).reduce(
        function(arr, key) {
            return arr.concat([key, root.properties[key]]);
        }, []
    )
    property string keyringLabel: Translation.tr("%1 Safe Storage").arg("illogical-impulse")

    property bool _pendingSave: false
    property bool _validRead: false

    function setNestedField(path, value) {
        // Never replace shared credentials with an unread or damaged snapshot.
        if (!root.loaded || !path || path.length === 0) {
            console.warn("[KeyringStorage] Storage not ready; edit was not saved.");
            root.fetchKeyringData();
            return;
        }
        if (!root.keyringData) root.keyringData = {};
        let keys = path;
        let obj = root.keyringData;
        let parents = [obj];

        // Traverse and collect parent objects
        for (let i = 0; i < keys.length - 1; ++i) {
            if (!obj[keys[i]] || typeof obj[keys[i]] !== "object") {
                obj[keys[i]] = {};
            }
            obj = obj[keys[i]];
            parents.push(obj);
        }

        // Set the value at the innermost key
        obj[keys[keys.length - 1]] = value;

        // Reassign each parent object from the bottom up to trigger change notifications
        for (let i = keys.length - 2; i >= 0; --i) {
            let parent = parents[i];
            let key = keys[i];
            // Shallow clone to change object identity (spread replaced with Object.assign)
            parent[key] = Object.assign({}, parent[key]);
        }

        // Finally, reassign root.keyringData to trigger top-level change
        root.keyringData = Object.assign({}, root.keyringData);

        saveKeyringData();
    }

    function fetchKeyringData() {
        // console.log("[KeyringStorage] Fetching keyring data...");
        // console.log("[KeyringStorage] getData command:'" + getData.command.join("' '") + "'");
        if (getData.running || saveData.running) return;
        root.loaded = false;
        root._validRead = false;
        getData.running = true;
    }

    function saveKeyringData() {
        if (!root.loaded) return;
        if (saveData.running) {
            root._pendingSave = true;
            return;
        }
        root._pendingSave = false;
        saveData.stdinEnabled = true;
        saveData.running = true;
    }

    Process {
        id: saveData
        command: [
            "secret-tool", "store", "--label=" + keyringLabel,
            ...propertiesAsArgs,
        ]
        onRunningChanged: {
            if (saveData.running) {
                // console.log("[KeyringStorage] Saving with command: '" + saveData.command.join("' '") + "'");
                saveData.write(JSON.stringify(root.keyringData));
                stdinEnabled = false // End input stream
            }
        }
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0) {
                root._pendingSave = false;
                root.loaded = false;
                console.warn("[KeyringStorage] Save failed; reload before editing again.");
                return;
            }
            if (root._pendingSave)
                Qt.callLater(root.saveKeyringData);
        }
    }

    Component.onCompleted: root.fetchKeyringData()

    Timer {
        id: retryTimer
        interval: 3000
        onTriggered: root.fetchKeyringData()
    }

    Process {
        id: getData
        command: [
            FileUtils.trimFileProtocol(`${Directories.scriptPath}/keyring/try_lookup.sh`)
        ]
        stderr: StdioCollector {
            onStreamFinished: {
                // Intentionally ignore stderr to match previous `2> /dev/null` behavior
            }
        }
        stdout: StdioCollector {
            id: keyringDataOutputCollector
            onStreamFinished: {
                try {
                    const parsed = JSON.parse(keyringDataOutputCollector.text);
                    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return;
                    root.keyringData = parsed; // Preserve all other consumers' fields.
                    root._validRead = true;
                } catch (e) {
                    // Keep existing credentials untouched, including malformed data.
                    root._validRead = false;
                }
            }
        }
        onExited: (exitCode, exitStatus) => {
            if (exitCode === 0 && root._validRead) {
                root.loaded = true;
            } else if (exitCode === 1) {
                // Helper confirmed an unlocked keyring and no matching entry.
                // Initialize in memory only; create it on an explicit user edit.
                root.keyringData = {};
                root.loaded = true;
            } else {
                root.loaded = false;
                if (exitCode === 2) retryTimer.restart();
                console.warn("[KeyringStorage] Shared storage unavailable; writes disabled.");
            }
        }
    }
    
}
