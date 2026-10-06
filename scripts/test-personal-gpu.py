#!/usr/bin/env python3
"""Exercise hybrid GPU selection and real launcher restoration in a fixture."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GPU_VARS = ['__NV_PRIME_RENDER_OFFLOAD', '__GLX_VENDOR_LIBRARY_NAME',
            '__VK_LAYER_NV_optimus', 'DRI_PRIME', '__EGL_VENDOR_LIBRARY_FILENAMES',
            'VK_LOADER_DRIVERS_DISABLE', 'MESA_VK_DEVICE_SELECT']


class GpuPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='inir-gpu-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / 'config'
        niri = self.config / 'niri/config.d'
        niri.mkdir(parents=True)
        (niri.parent / 'config.kdl').write_text(
            'include "config.d/40-environment.kdl"\ninclude "config.d/05-personal-gpu.kdl"\n')
        (niri / '40-environment.kdl').write_text('environment {\nQT_QPA_PLATFORM "wayland"\n}\n')
        self.gpu_config = niri / '05-personal-gpu.kdl'
        self.gpu_config.write_text(
            (ROOT / 'defaults/niri/config.d/05-personal-gpu.kdl').read_text()
            .replace('"compositor"', '"integrated"'))
        self.settings = self.base / 'config.json'
        self.settings.write_text('{"resources":{"monitorGpu":true}}')
        drm = self.base / 'drm'
        drm.mkdir()
        for number, pci, boot, vendor, device in [
            (1, '0000:06:00.0', '1', '0x1002', '0x1638'),
            (2, '0000:01:00.0', '0', '0x10de', '0x2520')]:
            card = drm / f'card{number}'
            card.mkdir()
            dev = self.base / pci
            dev.mkdir()
            (card / 'device').symlink_to(dev)
            for name, value in [('boot_vga', boot), ('vendor', vendor), ('device', device)]:
                (dev / name).write_text(value)
        launcher = (ROOT / 'scripts/inir').read_text()
        names = ['_niri_app_environment_file', '_niri_app_environment_value',
                 'apply_niri_app_environment', '_inir_set_shell_gpu_var', 'apply_gpu_policy']
        self.functions = '\n'.join(re.search(
            r'^' + name + r'\(\) \{.*?^\}', launcher, re.M | re.S)[0] for name in names)
        self.functions = self.functions.replace('/sys/class/drm/card*', str(drm / 'card*'))
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.config))
        for name in list(self.env):
            if name in GPU_VARS or name.startswith(('INIR_GPU_', 'INIR_SHELL_GPU_', 'MESA_VK_')):
                self.env.pop(name)

    def run_policy(self, extra='', mirror=True):
        script = self.functions + '\ninir_config_file() { printf "%s" ' + repr(str(self.settings)) + '; }\n'
        if mirror:
            script += 'apply_niri_app_environment\n'
        script += 'apply_gpu_policy\n' + extra + '\n'
        script += 'python3 -c ' + repr('import os,json; print(json.dumps({k:os.environ.get(k) for k in ' + repr(GPU_VARS) + '}))')
        return json.loads(subprocess.check_output(['bash', '-euc', script], env=self.env, text=True))

    def restore_fragment(self, manager=''):
        source = (ROOT / 'modules/common/functions/ShellExec.qml').read_text()
        fragment = source.split('            for _var in $INIR_SHELL_GPU_POLICY_VARS;', 1)[1]
        fragment = 'for _var in $INIR_SHELL_GPU_POLICY_VARS;' + fragment.split(
            '            # Fill missing user/session values', 1)[0]
        fragment = fragment.replace('\\${', '${')
        functions = source[source.index('            manager_value() {'):source.index('            import_if_missing() {')]
        return functions + '\nmanager_env=' + repr(manager) + '\n' + fragment

    def test_integrated_shell_does_not_disable_monitoring(self):
        before = self.settings.read_bytes()
        result = self.run_policy()
        self.assertEqual(result['__NV_PRIME_RENDER_OFFLOAD'], '0')
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'mesa')
        self.assertEqual(result['DRI_PRIME'], 'pci-0000_06_00_0')
        self.assertEqual(result['MESA_VK_DEVICE_SELECT'], '1002:1638')
        self.assertEqual(result['VK_LOADER_DRIVERS_DISABLE'], '*nvidia*')
        self.assertEqual(self.settings.read_bytes(), before)

    def test_application_recovers_niri_values_even_if_manager_is_stale(self):
        result = self.run_policy(self.restore_fragment('__GLX_VENDOR_LIBRARY_NAME=mesa'))
        self.assertEqual(result['__NV_PRIME_RENDER_OFFLOAD'], '1')
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'nvidia')
        self.assertEqual(result['__VK_LAYER_NV_optimus'], 'NVIDIA_only')
        for name in ['DRI_PRIME', '__EGL_VENDOR_LIBRARY_FILENAMES',
                     'VK_LOADER_DRIVERS_DISABLE', 'MESA_VK_DEVICE_SELECT']:
            self.assertIsNone(result[name])

    def test_empty_egl_placeholder_is_not_restored_to_launched_apps(self):
        self.env['__EGL_VENDOR_LIBRARY_FILENAMES'] = ''
        result = self.run_policy(self.restore_fragment() +
            '\n[[ -z "${INIR_SHELL_GPU_POLICY_VARS+x}" ]]\n' +
            '[[ -z "${INIR_GPU_APP___GLX_VENDOR_LIBRARY_NAME+x}" ]]')
        self.assertIsNone(result['__EGL_VENDOR_LIBRARY_FILENAMES'])

    def test_personal_compositor_policy_survives_disabled_gpu_monitoring(self):
        self.gpu_config.write_text(
            (ROOT / 'defaults/niri/config.d/05-personal-gpu.kdl').read_text())
        self.settings.write_text('{"resources":{"monitorGpu":false}}')
        self.env['__EGL_VENDOR_LIBRARY_FILENAMES'] = ''
        self.env['DRI_PRIME'] = ''
        result = self.run_policy()
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'nvidia')
        self.assertEqual(result['__NV_PRIME_RENDER_OFFLOAD'], '1')
        self.assertIsNone(result['__EGL_VENDOR_LIBRARY_FILENAMES'])
        self.assertIsNone(result['DRI_PRIME'])
        self.assertIsNone(result['VK_LOADER_DRIVERS_DISABLE'])

    def test_reapplying_policy_keeps_original_application_values(self):
        result = self.run_policy('apply_gpu_policy\n' + self.restore_fragment())
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'nvidia')

    def test_monitor_true_without_explicit_pin_keeps_upstream_behavior(self):
        result = self.run_policy(mirror=False)
        self.assertIsNone(result['DRI_PRIME'])
        self.assertIsNone(result['VK_LOADER_DRIVERS_DISABLE'])

    def test_monitor_false_is_not_lost_to_jq_default(self):
        self.settings.write_text('{"resources":{"monitorGpu":false}}')
        result = self.run_policy(mirror=False)
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'mesa')
        self.assertIsNone(result['DRI_PRIME'])

    def test_opt_out_retains_nvidia_app_defaults(self):
        self.env['INIR_GPU_FORCE_DEFAULT'] = '1'
        result = self.run_policy()
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'nvidia')
        self.assertIsNone(result['VK_LOADER_DRIVERS_DISABLE'])

    def test_nonhybrid_host_does_not_inject_shell_overrides(self):
        (self.base / 'drm/card2/device').unlink()
        result = self.run_policy()
        self.assertEqual(result['__GLX_VENDOR_LIBRARY_NAME'], 'nvidia')
        self.assertIsNone(result['VK_LOADER_DRIVERS_DISABLE'])


if __name__ == '__main__':
    unittest.main()
