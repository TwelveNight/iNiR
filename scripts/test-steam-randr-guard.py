#!/usr/bin/env python3
"""32-bit ABI test: inject the actual NULL RandR replies that crashed GTK2."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RandrGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.temp.name)
        def compile(name, text, options):
            source = cls.dir / (name + '.c')
            source.write_text(text)
            subprocess.run(['gcc', '-m32', '-Wall', '-Wextra', str(source), *options,
                            '-o', str(cls.dir / name)], check=True, capture_output=True)
        subprocess.run(['gcc', '-m32', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'scripts/personal/steam/gtk2-randr-guard.c'), '-ldl',
                        '-o', str(cls.dir / 'guard.so')], check=True)
        compile('backend.so', '''#include <X11/extensions/Xrandr.h>
#include <stdlib.h>
XRROutputInfo *XRRGetOutputInfo(Display*d,XRRScreenResources*r,RROutput o) {
 if (o != 99) return NULL;
 XRROutputInfo *p=calloc(1,sizeof(*p)); p->connection=RR_Connected; return p;
}
XRRCrtcInfo *XRRGetCrtcInfo(Display*d,XRRScreenResources*r,RRCrtc c) { return NULL; }
''', ['-shared', '-fPIC'])
        compile('libgdk-x11-2.0.so.fixture', '''#include <X11/extensions/Xrandr.h>
#include <stdlib.h>
int exercise(void) {
 XRROutputInfo *o=XRRGetOutputInfo(NULL,NULL,1);
 if (!o) return 10;
 if (o->connection!=RR_Disconnected || !o->name || *o->name) return 11;
 free(o);
 XRRCrtcInfo *c=XRRGetCrtcInfo(NULL,NULL,1);
 if (!c || c->width || c->height) return 12;
 free(c);
 o=XRRGetOutputInfo(NULL,NULL,99);
 if (!o || o->connection!=RR_Connected) return 13;
 free(o); return 0;
}
''', ['-shared', '-fPIC', '-L'+str(cls.dir), '-l:backend.so', '-Wl,-rpath,'+str(cls.dir)])
        compile('steam', '''#include <X11/extensions/Xrandr.h>
#include <stdlib.h>
#include <string.h>
extern int exercise(void);
int main(void) {
 if (getenv("LD_PRELOAD") || getenv("INIR_STEAM_PREVIOUS_PRELOAD")) return 20;
 /* Calls from outside GTK2 retain the original NULL result. */
 if (XRRGetOutputInfo(NULL,NULL,1)!=NULL) return 21;
 return exercise();
}
''', ['-L'+str(cls.dir), '-l:libgdk-x11-2.0.so.fixture', '-l:backend.so', '-Wl,-rpath,'+str(cls.dir)])
        (cls.dir / 'other-app').write_bytes((cls.dir / 'steam').read_bytes())
        (cls.dir / 'other-app').chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_client(self, name):
        return subprocess.run([str(self.dir / name)], env=dict(os.environ,
                              LD_PRELOAD=str(self.dir / 'guard.so'), INIR_STEAM_PREVIOUS_PRELOAD=''),
                              capture_output=True, text=True)

    def test_steam_gtk_null_output_and_crtc_success_and_child_env(self):
        result = self.run_client('steam')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('vanished output', result.stderr)
        self.assertIn('vanished CRTC', result.stderr)

    def test_other_application_is_not_patched(self):
        self.assertEqual(self.run_client('other-app').returncode, 10)


if __name__ == '__main__':
    unittest.main()
