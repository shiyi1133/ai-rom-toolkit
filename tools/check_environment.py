"""Check the bundled Windows executables without installing or changing the system."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--report',type=Path)
    parser.add_argument('--require-headless',action='store_true',help='Require the separately supplied custom backend')
    args=parser.parse_args()
    tools={
      'python':(Path(sys.executable),['--version']),
      'arm-gcc':(ROOT/'runtime/arm/bin/arm-none-eabi-gcc.exe',['--version']),
      'arm-as':(ROOT/'runtime/arm/bin/arm-none-eabi-as.exe',['--version']),
      'arm-ld':(ROOT/'runtime/arm/bin/arm-none-eabi-ld.exe',['--version']),
      'arm-objcopy':(ROOT/'runtime/arm/bin/arm-none-eabi-objcopy.exe',['--version']),
      'arm-objdump':(ROOT/'runtime/arm/bin/arm-none-eabi-objdump.exe',['--version']),
      'rgbasm':(ROOT/'runtime/rgbds/rgbasm.exe',['-V']),
      'rgblink':(ROOT/'runtime/rgbds/rgblink.exe',['-V']),
      'rgbfix':(ROOT/'runtime/rgbds/rgbfix.exe',['-V']),
      'rgbgfx':(ROOT/'runtime/rgbds/rgbgfx.exe',['-V']),
      'mgba-sdl':(ROOT/'runtime/mgba/mgba-sdl.exe',['--version'])}
    result=dict(os=platform.platform(),python=sys.version,windows_native=os.name=='nt',checks={})
    for name,(exe,arguments) in tools.items():
        try:
            p=subprocess.run([str(exe),*arguments],capture_output=True,text=True,errors='replace',timeout=20)
            lines=(p.stdout+p.stderr).strip().splitlines()
            ok=p.returncode==0
            result['checks'][name]=dict(ok=ok,exit_code=p.returncode,
                version=lines[0] if lines else '',path=str(exe),probe='version')
        except Exception as exc: result['checks'][name]=dict(ok=False,error=str(exc),path=str(exe))
    mgba=ROOT/'runtime/mgba/mGBA.exe'
    result['mgba_gui']=dict(exists=mgba.is_file(),sha256=hashlib.sha256(mgba.read_bytes()).hexdigest() if mgba.is_file() else None)
    headless=ROOT/'tools/windows_mgba/bin/mgba-headless.exe'
    gdb=ROOT/'tools/windows_mgba/bin/mgba-headless-gdb.exe'
    optional=dict(available=headless.is_file() and gdb.is_file(),validated=False,
                  status='not_available',reason='Custom binaries are not distributed by this source repository')
    if optional['available']:
        try:
            p=subprocess.run([str(headless),'--help'],capture_output=True,text=True,errors='replace',timeout=20)
            optional.update(validated=p.returncode==1 and 'Generic options:' in p.stdout+p.stderr,
                            status='loadability_checked',exit_code=p.returncode)
        except Exception as exc:optional.update(status='failed',error=str(exc))
    result['optional_headless']=optional
    result['ok']=bool(result['windows_native'] and result['mgba_gui']['exists'] and all(x['ok'] for x in result['checks'].values())
                      and (not args.require_headless or optional['validated']))
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result['ok'] else 1

if __name__=='__main__': raise SystemExit(main())
