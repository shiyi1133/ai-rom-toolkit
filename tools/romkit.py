"""Standard-library ROM identity, isolated initialization, and guarded byte patches."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import zlib
from pathlib import Path


def identity(path):
    path = Path(path).resolve(strict=True)
    sha, md5, crc, size = hashlib.sha256(), hashlib.md5(), 0, 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            sha.update(chunk); md5.update(chunk)
            crc = zlib.crc32(chunk, crc); size += len(chunk)
    return dict(size=size, sha256=sha.hexdigest(), md5=md5.hexdigest(), crc32=f'{crc & 0xffffffff:08X}')


def new_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(value, out, ensure_ascii=False, indent=2); out.write('\n')


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('Offsets must be integers or integer strings.')
    return int(value, 0) if isinstance(value, str) else int(value)


def initialize(args):
    src = args.rom.resolve(strict=True)
    platform = args.platform.upper()
    dest = args.project.resolve()
    if dest.exists():
        raise ValueError('Project directory already exists; use a new project name.')
    if src.suffix.lower() not in ('.gba', '.gb', '.gbc'):
        raise ValueError('Expected an uncompressed .gba, .gb, or .gbc file.')
    ident = identity(src)
    save = args.save.resolve(strict=True) if args.save else None
    dest.mkdir(parents=True, exist_ok=False)
    for folder in ('input', 'output', 'saves', 'records', 'text', 'fonts', 'analysis', 'runtime', 'patches'):
        (dest / folder).mkdir()
    base = dest / 'input' / ('base.' + platform.lower())
    shutil.copyfile(src, base)
    assert identity(base) == ident
    record = dict(schema_version=1, name=args.name or dest.name, platform=platform,
                  base_rom=base.relative_to(dest).as_posix(), identity=ident,
                  source_rom=str(src), status='initialized', gameplay_validation='not_run')
    if save:
        save_copy = dest / 'saves' / 'original.sav'
        shutil.copyfile(save, save_copy)
        record['save'] = dict(path='saves/original.sav', source=str(save), identity=identity(save_copy))
    new_json(dest / 'project.json', record)
    toolkit = Path(__file__).resolve().parents[1]
    shutil.copyfile(toolkit / 'templates' / 'PROJECT_RULES.txt', dest / 'AGENTS.md')
    shutil.copyfile(toolkit / 'templates' / 'TEST_ACCEPTANCE.txt', dest / 'records' / 'TEST_ACCEPTANCE.txt')
    return dict(project=str(dest), **record)


def guarded_patch(args):
    src = args.rom.resolve(strict=True)
    definition = json.loads(args.definition.read_text(encoding='utf-8-sig'))
    before_id = identity(src)
    expected = definition.get('base_sha256', '')
    if not isinstance(expected, str) or len(expected) != 64 or expected.lower() != before_id['sha256']:
        raise ValueError('Base SHA-256 mismatch or missing. No output was written.')
    data = bytearray(src.read_bytes())
    writes, spans, records = definition.get('writes'), [], []
    if not isinstance(writes, list) or not writes:
        raise ValueError('writes must be a nonempty list.')
    for item in writes:
        offset = number(item['offset'])
        old = bytes.fromhex(item['before_hex'])
        new = bytes.fromhex(item['after_hex'])
        if not old or len(old) != len(new):
            raise ValueError('Each write must have nonempty, equal-sized before and after bytes.')
        end = offset + len(old)
        if offset < 0 or end > len(data):
            raise ValueError(f'Write out of bounds at {offset:#x}.')
        if any(offset < b and a < end for a, b in spans):
            raise ValueError(f'Overlapping writes at {offset:#x}.')
        if bytes(data[offset:end]) != old:
            raise ValueError(f'Preimage mismatch at {offset:#x}. No output was written.')
        spans.append((offset, end))
        records.append(dict(offset=offset, before_hex=old.hex(), after_hex=new.hex(), note=item.get('note', '')))
    # Validate every preimage before changing even the in-memory copy.
    for item in records:
        offset = item['offset']; new = bytes.fromhex(item['after_hex'])
        data[offset:offset + len(new)] = new
    output = args.output.resolve()
    report = output.with_name(output.name + '.patch-report.json')
    if output == src or output.exists() or report.exists():
        raise ValueError('Refusing to overwrite an input, existing output, or existing report.')
    # Recheck the input after validation to detect changes by another writer.
    if identity(src) != before_id:
        raise ValueError('Input changed during validation.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(data)
    result = dict(schema_version=1, base=before_id, output=identity(output),
                  writes=records, gameplay_validation='not_run')
    new_json(report, result)
    return dict(output_path=str(output), report_path=str(report), **result)


def differences(args):
    a, b = args.base.read_bytes(), args.modified.read_bytes()
    ranges, start, count = [], None, 0
    for i in range(max(len(a), len(b))):
        different = i >= len(a) or i >= len(b) or a[i] != b[i]
        if different:
            count += 1
            if start is None: start = i
        elif start is not None:
            ranges.append(dict(start=start, end_exclusive=i, length=i-start)); start=None
    if start is not None:
        ranges.append(dict(start=start, end_exclusive=max(len(a),len(b)), length=max(len(a),len(b))-start))
    result = dict(base=identity(args.base), modified=identity(args.modified), changed_positions=count,
                  range_count=len(ranges), ranges=ranges[:args.limit], truncated=len(ranges)>args.limit)
    if args.report: new_json(args.report, result)
    return result


def bank_offset(args):
    bank, address = number(args.bank), number(args.address)
    if bank == 0 and 0 <= address < 0x4000:
        offset = address
    elif bank >= 1 and 0x4000 <= address < 0x8000:
        offset = bank * 0x4000 + address - 0x4000
    else:
        raise ValueError('ROM0 uses bank=0/address=0..0x3fff; ROMX uses physical bank>=1/address=0x4000..0x7fff.')
    return dict(physical_bank=bank, cpu_address=f'0x{address:04X}', file_offset=offset,
                file_offset_hex=f'0x{offset:X}', note='Physical bank mapping only; MBC register values require separate analysis.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command', required=True)
    p=subs.add_parser('identity'); p.add_argument('rom', type=Path)
    p=subs.add_parser('init'); p.add_argument('rom', type=Path)
    p.add_argument('--project', required=True, type=Path); p.add_argument('--platform', choices=['gba','gb','gbc'], required=True)
    p.add_argument('--name'); p.add_argument('--save', type=Path)
    p=subs.add_parser('patch'); p.add_argument('rom', type=Path); p.add_argument('definition', type=Path); p.add_argument('output', type=Path)
    p=subs.add_parser('diff'); p.add_argument('base',type=Path); p.add_argument('modified',type=Path)
    p.add_argument('--report',type=Path); p.add_argument('--limit',type=int,default=2000)
    p=subs.add_parser('bank-offset'); p.add_argument('--bank',required=True); p.add_argument('--address',required=True)
    args=parser.parse_args()
    try:
        result={'identity':lambda x:identity(x.rom),'init':initialize,'patch':guarded_patch,
                'diff':differences,'bank-offset':bank_offset}[args.command](args)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr); return 1


if __name__=='__main__': raise SystemExit(main())
