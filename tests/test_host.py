"""Prevent toolchain paths from mixing Windows and Linux installations."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import toolkit_host as host


class HostTests(unittest.TestCase):
    def test_host_paths_and_appimage_mode(self):
        for name in ('linux', 'windows'):
            with self.subTest(host=name), patch.object(host, 'host_name', return_value=name):
                runtime = host.ROOT/'runtime'/'linux' if name == 'linux' else host.ROOT/'runtime'
                suffix = '' if name == 'linux' else '.exe'
                self.assertEqual(host.arm_tool('gcc'), runtime/'arm/bin'/('arm-none-eabi-gcc'+suffix))
                self.assertEqual(host.rgb_tool('rgbasm'), runtime/'rgbds'/('rgbasm'+suffix))
                self.assertEqual('--appimage-extract-and-run' in host.mgba_command(), name == 'linux')

    def test_other_architecture_is_rejected(self):
        with patch.object(host.platform, 'machine', return_value='aarch64'):
            with self.assertRaisesRegex(RuntimeError, 'x86_64'): host.require_supported_host()
