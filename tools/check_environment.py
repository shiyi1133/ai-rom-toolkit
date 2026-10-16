"""Probe checkout-local host executables; never install or change system configuration."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from toolkit_host import arm_tool, rgb_tool, mgba_command, require_supported_host, runtime_root

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    parser.add_argument('--require-headless', action='store_true', help='Require the separately supplied Windows custom backend')
    args = parser.parse_args()
    host = require_supported_host()
    probes = {'python': [sys.executable, '--version']}
    probes.update({f'arm-{name}': [str(arm_tool(name)), '--version'] for name in ('gcc', 'as', 'ld', 'objcopy', 'objdump')})
    probes.update({name: [str(rgb_tool(name)), '-V'] for name in ('rgbasm', 'rgblink', 'rgbfix', 'rgbgfx')})
    probes['mgba'] = [*mgba_command(), '--version']
    result = dict(os=platform.platform(), python=sys.version, host=host, windows_native=os.name == 'nt',
                  linux_native=sys.platform == 'linux', checks={})
    env = os.environ.copy()
    if host == 'linux':
        # --version proves executable loadability, not a working display or gameplay.
        env['QT_QPA_PLATFORM'] = 'offscreen'
    for name, command in probes.items():
        try:
            p = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=30, env=env)
            lines = (p.stdout + p.stderr).strip().splitlines()
            result['checks'][name] = dict(ok=p.returncode == 0, exit_code=p.returncode,
                version=lines[0] if lines else '', path=command[0], probe='version',
                detail='\n'.join(lines[:8]))
        except Exception as exc:
            result['checks'][name] = dict(ok=False, error=str(exc), path=command[0])
    mgba = runtime_root() / 'mgba' / ('mGBA.exe' if host == 'windows' else 'mgba.AppImage')
    result['mgba_gui'] = dict(exists=mgba.is_file(), sha256=hashlib.sha256(mgba.read_bytes()).hexdigest() if mgba.is_file() else None,
                              display_test='not_run', gameplay='not_run')
    headless = ROOT / 'tools/windows_mgba/bin/mgba-headless.exe'
    gdb = ROOT / 'tools/windows_mgba/bin/mgba-headless-gdb.exe'
    optional = dict(available=host == 'windows' and headless.is_file() and gdb.is_file(), validated=False,
                    status='not_available', reason='Custom backend is Windows-only and is not distributed by this repository')
    if optional['available']:
        try:
            p = subprocess.run([str(headless), '--help'], capture_output=True, text=True, errors='replace', timeout=20)
            optional.update(validated=p.returncode == 1 and 'Generic options:' in p.stdout + p.stderr,
                            status='loadability_checked', exit_code=p.returncode)
        except Exception as exc:
            optional.update(status='failed', error=str(exc))
    result['optional_headless'] = optional
    result['ok'] = bool(result['mgba_gui']['exists'] and all(x['ok'] for x in result['checks'].values())
                        and (not args.require_headless or optional['validated']))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
