#!/usr/bin/env python3
"""Exercise the real QML backend offscreen against an isolated skwd client."""
import os, signal, subprocess, tempfile, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='inir-qs-test-') as tmp:
 p=Path(tmp); (p/'services').mkdir(); (p/'modules/common').mkdir(parents=True);(p/'bin').mkdir();(p/'runtime').mkdir(mode=0o700)
 for n in ['SkwdBackend.qml','skwdState.js']:(p/'services'/n).write_text((root/'services'/n).read_text())
 (p/'services/qmldir').write_text('singleton SkwdBackend 1.0 SkwdBackend.qml\n')
 (p/'modules/common/qmldir').write_text('singleton Directories 1.0 Directories.qml\n')
 (p/'modules/common/Directories.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { readonly property string homePath: "/tmp" }\n')
 mock=p/'bin/skwd-helm';mock.write_text('''#!/usr/bin/env python3
import sys,json,time,os
from pathlib import Path
p=Path(os.environ['MOCK_DIR'])
if sys.argv[1]=='current':
 print(json.dumps({'outputs':[{'name':'eDP-2','connected':True,'path':'/external.png' if (p/'event').exists() else '/original.png'}]}))
elif sys.argv[1]=='apply':
 time.sleep(.15)
 if sys.argv[2]=='/fail.png':sys.exit(7)
 with (p/'applies').open('a') as f:f.write(sys.argv[2]+'\\n')
elif sys.argv[1]=='watch':
 (p/'watch.pid').write_text(str(os.getpid()))
 if os.environ.get('MOCK_HOLD')=='1': time.sleep(30); sys.exit(0)
 time.sleep(1.5)
 (p/'event').touch()
 print(json.dumps({'event':'skwd.wall.applied'}),flush=True)
 time.sleep(30)
''');mock.chmod(0o755)
 (p/'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
ShellRoot {
 id: root
 property int stage: 0
 property int ticks: 0
 property var successes: []
 Connections { target: SkwdBackend; function onApplied(path, monitor) { root.successes.push(path) } }
 Timer {
  running: true; repeat: true; interval: 50
  onTriggered: {
   root.ticks++
   if (Quickshell.env("MOCK_HOLD") === "1") return
   if (root.ticks > 100) { console.error("FAIL timeout stage="+root.stage+" error="+SkwdBackend.lastError); Qt.quit(); return }
   if (root.stage === 0 && SkwdBackend.available) {
    if (SkwdBackend.wallpaperPath("eDP-2") !== "/original.png") { console.error("FAIL initial"); Qt.quit(); return }
    SkwdBackend.apply("/fail.png"); root.stage=1
   } else if (root.stage === 1 && SkwdBackend.lastError.includes("(7)")) {
    if (root.successes.length !== 0) { console.error("FAIL failed apply emitted success"); Qt.quit(); return }
    SkwdBackend.apply("/first.mp4"); SkwdBackend.apply("/discarded.png"); SkwdBackend.apply("/latest.gif"); root.stage=2
   } else if (root.stage === 2 && root.successes.length >= 2 && SkwdBackend.wallpaperPath("eDP-2") === "/external.png") {
    if (JSON.stringify(root.successes) !== '["/first.mp4","/latest.gif"]') console.error("FAIL queue "+JSON.stringify(root.successes))
    else console.log("PASS state query, failure, latest request queue, watch event")
    Qt.quit()
   }
  }
 }
}''')
 env=dict(os.environ,QT_QPA_PLATFORM='offscreen',XDG_RUNTIME_DIR=str(p/'runtime'),XDG_CONFIG_HOME=str(p/'config'),XDG_STATE_HOME=str(p/'state'),XDG_CACHE_HOME=str(p/'cache'),MOCK_DIR=tmp,PATH=str(p/'bin')+':'+os.environ['PATH'])
 result=subprocess.run(['qs','-p',str(p),'--no-color'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
 print(result.stdout)
 assert 'PASS state query' in result.stdout
 assert 'FAIL' not in result.stdout
 assert (p/'applies').read_text().splitlines()==['/first.mp4','/latest.gif']

 # Closing settings or restarting the service must not leave its watch client
 # behind. In particular, SIGTERM/SIGKILL need not run QML destructors.
 def alive(pid):
  try:
   return Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1][0] != 'Z'
  except FileNotFoundError:
   return False

 def wait_dead(pid):
  deadline=time.monotonic()+2
  while alive(pid) and time.monotonic()<deadline: time.sleep(.02)
  return not alive(pid)

 assert wait_dead(int((p/'watch.pid').read_text())), 'Watcher survived normal QML exit'
 for stop_signal in (signal.SIGTERM, signal.SIGKILL):
  (p/'watch.pid').unlink()
  process=subprocess.Popen(['qs','-p',str(p),'--no-color'],env=dict(env,MOCK_HOLD='1',QS_DISABLE_CRASH_HANDLER='1'),
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  pid=None
  try:
   deadline=time.monotonic()+5
   while not (p/'watch.pid').exists() and time.monotonic()<deadline:
    assert process.poll() is None, 'Quickshell failed before watch started'
    time.sleep(.02)
   pid=int((p/'watch.pid').read_text())
   assert alive(pid), 'Watch client did not start'
   process.send_signal(stop_signal)
   process.wait(timeout=3)
   assert wait_dead(pid), f'Watcher survived Quickshell {stop_signal.name}'
  finally:
   if process.poll() is None:
    process.kill(); process.wait(timeout=3)
   if pid is not None and alive(pid): os.kill(pid,signal.SIGKILL)
 print('PASS watch cleanup after QML exit, SIGTERM and SIGKILL')
