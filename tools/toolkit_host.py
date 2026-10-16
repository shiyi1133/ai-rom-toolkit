"""Resolve checkout-local tools for the actual executing OS, never by PATH fallback."""
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]


def host_name():
    if os.name == 'nt':
        return 'windows'
    if sys.platform == 'linux':
        return 'linux'
    raise RuntimeError('Supported initialization targets: Windows x64 and Linux x86_64')


def require_supported_host():
    name = host_name()
    if platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('Pinned dependencies require x86_64; other architectures are not supported')
    if name == 'linux' and sys.version_info < (3, 12):
        raise RuntimeError('Linux initialization requires an existing Python 3.12+ (safe tar extraction)')
    return name


def runtime_root():
    return ROOT / 'runtime' / 'linux' if host_name() == 'linux' else ROOT / 'runtime'


def arm_tool(name):
    return runtime_root() / 'arm' / 'bin' / ('arm-none-eabi-' + name + ('.exe' if host_name() == 'windows' else ''))


def rgb_tool(name):
    return runtime_root() / 'rgbds' / (name + ('.exe' if host_name() == 'windows' else ''))


def mgba_command():
    if host_name() == 'linux':
        # The official AppImage runtime extracts locally without requiring FUSE.
        return [str(runtime_root() / 'mgba' / 'mgba.AppImage'), '--appimage-extract-and-run']
    return [str(runtime_root() / 'mgba' / 'mgba-sdl.exe')]
