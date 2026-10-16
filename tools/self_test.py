"""Host-native toolchain smoke tests using only generated homebrew ROMs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from romkit import identity
from toolkit_host import arm_tool, rgb_tool, require_supported_host

ROOT=Path(__file__).resolve().parents[1]

def run(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
    if p.returncode:
        raise RuntimeError(f'Command failed ({p.returncode}): {args[0]}\n{p.stdout}\n{p.stderr}')
    return p.stdout.strip()

def rejected(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,timeout=15)
    if p.returncode==0: raise AssertionError('Invalid input was accepted.')

def build_roms(base):
    out={}
    obj,elf,rom=base/'gba.o',base/'gba.elf',base/'自制测试.gba'
    run([arm_tool('as'),'-mcpu=arm7tdmi',ROOT/'examples/gba/smoke.s','-o',obj])
    run([arm_tool('ld'),'-Ttext=0x08000000','-e','_start',obj,'-o',elf])
    run([arm_tool('objcopy'),'-O','binary',elf,rom])
    data=bytearray(rom.read_bytes())
    data.extend(b'\xff'*(32768-len(data)))
    data[0xa0:0xac]=b'ROMKIT TEST '
    data[0xac:0xb0]=b'TSTE'; data[0xb0:0xb2]=b'00'; data[0xb2]=0x96
    data[0xbd]=(-sum(data[0xa0:0xbd])-0x19)&255
    data[0x200:0x209]=b'SRAM_V113'
    rom.write_bytes(data); out['GBA']=rom
    # Compiler compatibility is tested on a freestanding ARM7TDMI Thumb C fragment.
    c=base/'fragment.c'; c.write_text('int sample(int value) { return value + 1; }\n',encoding='ascii')
    run([arm_tool('gcc'),'-mcpu=arm7tdmi','-mthumb','-mthumb-interwork','-mfloat-abi=soft',
         '-ffreestanding','-fno-builtin','-c',c,'-o',base/'fragment.o'])
    disassembly=run([arm_tool('objdump'),'-d',base/'fragment.o'])
    if 'sample' not in disassembly: raise AssertionError('GBA object disassembly failed.')
    for platform in ('GB','GBC'):
        obj=base/(platform.lower()+'.o'); rom=base/('自制测试.'+platform.lower())
        run([rgb_tool('rgbasm'),'-o',obj,ROOT/'examples'/platform.lower()/'smoke.asm'])
        run([rgb_tool('rgblink'),'-o',rom,obj])
        flags=['-v','-p','0','-t','ROMKIT TEST','-m','0x03','-r','2']+(['-C'] if platform=='GBC' else [])
        run([rgb_tool('rgbfix'),*flags,rom]); out[platform]=rom
    return out

def patch_tests(base,rom):
    toolkit=ROOT/'tools/romkit.py'; py=Path(sys.executable)
    before=identity(rom)
    definition=base/'patch.json'
    raw=rom.read_bytes()
    item=dict(offset=0x200,before_hex=raw[0x200:0x204].hex(),after_hex='01020304')
    d=dict(base_sha256=before['sha256'],writes=[item])
    definition.write_text(json.dumps(d),encoding='utf-8')
    output=base/'新的 输出.gba'
    run([py,toolkit,'patch',rom,definition,output])
    data=output.read_bytes()
    assert data[:0x200]==raw[:0x200] and data[0x200:0x204]==b'\x01\x02\x03\x04' and data[0x204:]==raw[0x204:]
    rejected([py,toolkit,'patch',rom,definition,rom])
    rejected([py,toolkit,'patch',rom,definition,output])
    d['base_sha256']='0'*64; definition.write_text(json.dumps(d))
    rejected([py,toolkit,'patch',rom,definition,base/'bad-hash.gba'])
    d['base_sha256']=before['sha256']; d['writes'][0]['before_hex']='00000000';definition.write_text(json.dumps(d))
    rejected([py,toolkit,'patch',rom,definition,base/'bad-preimage.gba'])
    d['writes']=[item,item]; item['before_hex']=raw[0x200:0x204].hex(); definition.write_text(json.dumps(d))
    rejected([py,toolkit,'patch',rom,definition,base/'overlap.gba'])
    d['writes']=[dict(offset=len(raw),before_hex='ff',after_hex='00')];definition.write_text(json.dumps(d))
    rejected([py,toolkit,'patch',rom,definition,base/'bounds.gba'])
    d['writes']=[dict(offset=0x200,before_hex='ff',after_hex='0000')];definition.write_text(json.dumps(d))
    rejected([py,toolkit,'patch',rom,definition,base/'length.gba'])
    assert not any((base/n).exists() for n in ['bad-hash.gba','bad-preimage.gba','overlap.gba','bounds.gba','length.gba'])
    diff=json.loads(run([py,toolkit,'diff',rom,output])); assert diff['changed_positions']==4
    mapping=json.loads(run([py,toolkit,'bank-offset','--bank','3','--address','0x4567']))
    assert mapping['file_offset']==0xc567
    project=base/'Chinese 路径'/'new project'
    run([py,toolkit,'init',rom,'--platform','gba','--project',project])
    assert json.loads((project/'project.json').read_text(encoding='utf-8'))['identity']==before
    rejected([py,toolkit,'init',rom,'--platform','gba','--project',project])
    assert identity(rom)==before
    return dict(ok=True,changed_positions=4,rejection_checks=['input overwrite','output overwrite','wrong SHA-256',
                 'wrong preimage','overlap','out of bounds','unequal length','existing project'],
                unicode_and_spaces=True,source_unchanged=True,gb_physical_bank_mapping=True)

def emulator_test(base,platform,rom):
    sys.path.insert(0, str(ROOT/'tools/windows_mgba'))
    from mgba_client import send_commands
    py=Path(sys.executable); manager=ROOT/'tools/windows_mgba/windows_mgba_service.py'
    runtime=base/'path with spaces'/'runtime'; runtime.mkdir(parents=True,exist_ok=True)
    common=[py,manager,'--runtime-root',runtime]
    instance=platform.lower(); session=runtime/instance/'session.json'
    source_save=base/('原始测试存档_'+instance+'.sav')
    source_save.write_bytes(bytes([0xa5])+bytes([0xff])*8191)
    before=dict(rom=identity(rom),save=identity(source_save))
    result=dict(platform=platform,ok=False)
    started=[]
    try:
        run([*common,'start','--instance',instance,'--rom',rom,'--save',source_save,'--paused'])
        started.append(instance)
        config=json.loads(session.read_text(encoding='utf-8'))
        inst=Path(config['rom_copy']).parent.parent
        read_addr=0x08000000 if platform=='GBA' else 0x100
        responses=send_commands(session,['PING','FRAMES',f'READBLOCK {read_addr:#x} 16'],5)
        assert responses[0]=='PONG' and responses[1]=='OK 0' and responses[2].startswith('OK '),responses
        # Authentication failure must be observable, not just inferred from a token.
        with socket.create_connection((config['host'],int(config['lua_port'])),2) as sock:
            sock.sendall(b'PING\n'); assert sock.recv(256).strip()==b'ERR AUTH'
        dump=inst/'analysis/header.bin'
        response=send_commands(session,[f'DUMPBLOCK {read_addr:#x} 16 {dump.as_posix()}'],5)[0]
        assert response.startswith('OK ') and dump.read_bytes()==rom.read_bytes()[0 if platform=='GBA' else 0x100:16 if platform=='GBA' else 0x110]
        run([*common,'frame','--instance',instance,'1'])
        shot=inst/'screenshots/smoke.png'; state=inst/'savestates/smoke.ss1'
        responses=send_commands(session,['FRAMES',f'SHOT {shot.as_posix()}',f'SAVESTATE {state.as_posix()}'],10)
        assert responses[0]=='OK 1' and shot.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and state.stat().st_size>0,responses
        send_commands(session,['KEYS 0x001 3'],5)
        run([*common,'frame','--instance',instance,'3'])
        assert send_commands(session,['FRAMES'],5)==['OK 4']
        expected_dimensions=(240,160) if platform=='GBA' else (160,144)
        png=shot.read_bytes(); dimensions=(int.from_bytes(png[16:20],'big'),int.from_bytes(png[20:24],'big'))
        assert dimensions==expected_dimensions,dimensions
        # Prove that the configured save path is the isolated copy location.
        assert any('savegamePath='+str(inst/'saves')==str(x) for x in config['command'])
        save_address=0x0e000000 if platform=='GBA' else 0xa000
        loaded=send_commands(session,[f'READ8 {save_address:#x}'],5)[0]
        assert loaded.split()[-1].lower()=='a5', f'Isolated ordinary save was not loaded: {loaded}'
        if platform=='GBA':
            name='gdb';run([*common,'start','--instance',name,'--rom',rom,'--mode','gdb']);started.append(name)
            gdb=json.loads((runtime/name/'session.json').read_text(encoding='utf-8'))
            with socket.create_connection((gdb['host'],int(gdb['gdb_port'])),3) as sock:
                sock.settimeout(3);sock.sendall(b'$?#3f'); reply=bytearray()
                while b'#' not in reply: reply.extend(sock.recv(4096))
                assert b'$S02#' in reply,reply
            result['gdb_stop_reply']='S02'
        else:
            assert send_commands(session,['TRACE_PC_START 0x100 10'],5)==['ERR GBA_ONLY']
        result.update(ok=True,paused_frame_0=True,single_frame=True,keys_three_frames=True,
                      authenticated=True,block_dump=True,screenshot_dimensions=dimensions,savestate=True,
                      isolated_save_path=True,ordinary_save_loaded=True,source_hashes=before)
    finally:
        for name in reversed(started):
            run([*common,'stop','--instance',name])
    assert dict(rom=identity(rom),save=identity(source_save))==before
    result['source_hashes_unchanged']=True
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);parser.add_argument('--keep',action='store_true')
    parser.add_argument('--with-headless',action='store_true',help='Test a separately supplied compatible custom backend')
    args=parser.parse_args()
    host = require_supported_host()
    if args.with_headless and host != 'windows':
        parser.error('The optional custom backend is Windows-only; Linux emulator acceptance is not implemented')
    if args.with_headless and not str(ROOT).isascii():
        raise SystemExit('Headless self-test requires an ASCII toolkit path, as documented.')
    parent=ROOT/'workspace/runtime';parent.mkdir(parents=True,exist_ok=True)
    base=Path(tempfile.mkdtemp(prefix='self_test_',dir=parent)).resolve()
    report=args.report or ROOT/'reports'/('self_test_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
    result=dict(scope='toolchain and optional emulator infrastructure only; no commercial-game acceptance',host=host,ok=False,checks={})
    try:
        roms=build_roms(base);result['checks']['homebrew_builds']={k:identity(v) for k,v in roms.items()}
        result['checks']['guarded_patch']=patch_tests(base,roms['GBA'])
        if args.with_headless:
            result['checks']['emulator']={}
            for platform,rom in roms.items():
                result['checks']['emulator'][platform]=emulator_test(base,platform,rom)
        else:
            result['checks']['emulator']=dict(status='not_run',reason='Optional custom headless backend was not requested')
        result['ok']=True
    except Exception as exc:
        result['error']=str(exc)
    finally:
        report.parent.mkdir(parents=True,exist_ok=True)
        with report.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        if not args.keep:
            for attempt in range(20):
                try:shutil.rmtree(base);break
                except PermissionError:time.sleep(0.1)
        else:result['retained_runtime']=str(base)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('Report:',report);return 0 if result['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
