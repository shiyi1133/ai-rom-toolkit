"""Read BDF/Unifont HEX; check coverage, preview, and export monochrome ROM glyphs.

No external packages. This tool never opens or modifies a game ROM.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class Glyph:
    width: int
    height: int
    x_offset: int
    y_offset: int
    advance: int
    rows: list[int]

class Font:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.glyphs = {}
        self.width = self.height = self.ascent = 0
        if self.path.suffix.lower() == '.bdf': self._bdf()
        elif self.path.suffix.lower() == '.hex': self._hex()
        else: raise ValueError('Use the supplied .bdf or .hex bitmap font, not TTF/OTF.')
        if not self.glyphs or min(self.width, self.height) <= 0:
            raise ValueError('Empty font or invalid font metrics.')

    def _bdf(self):
        current = None
        bitmap = False
        with self.path.open(encoding='utf-8-sig', errors='replace') as stream:
            for raw in stream:
                line = raw.strip()
                if line.startswith('FONTBOUNDINGBOX '):
                    w, h, x, y = map(int, line.split()[1:])
                    self.width, self.height, self.ascent = w, h, h+y
                elif line.startswith('FONT_ASCENT '):
                    self.ascent = int(line.split()[1])
                elif line.startswith('STARTCHAR '):
                    current = {'encoding': -1, 'rows': []}; bitmap = False
                elif line == 'ENDCHAR' and current is not None:
                    cp = current['encoding']
                    if 0 <= cp <= 0x10ffff:
                        w,h,x,y = current['box']
                        if len(current['rows']) != h: raise ValueError(f'Invalid BDF row count at U+{cp:04X}.')
                        if cp in self.glyphs: raise ValueError(f'Duplicate BDF encoding U+{cp:04X}.')
                        self.glyphs[cp] = Glyph(w,h,x,y,current.get('advance',w),current['rows'])
                    current = None; bitmap = False
                elif current is not None:
                    if line.startswith('ENCODING '): current['encoding'] = int(line.split()[1])
                    elif line.startswith('DWIDTH '): current['advance'] = int(line.split()[1])
                    elif line.startswith('BBX '): current['box'] = tuple(map(int,line.split()[1:]))
                    elif line == 'BITMAP': bitmap = True
                    elif bitmap:
                        width = current['box'][0]
                        stride = (width+7)//8
                        if len(line) != stride*2: raise ValueError('Invalid BDF bitmap width.')
                        current['rows'].append(int(line,16) >> (stride*8-width) if width else 0)

    def _hex(self):
        self.width = self.height = self.ascent = 16
        with self.path.open(encoding='ascii') as stream:
            for raw in stream:
                line = raw.strip()
                if not line or line.startswith('#'): continue
                code, data = line.split(':',1); cp = int(code,16)
                if len(data) not in (32,64): raise ValueError('Expected 8x16 or 16x16 Unifont HEX glyph.')
                if cp in self.glyphs: raise ValueError(f'Duplicate HEX encoding U+{cp:04X}.')
                w = len(data)//4
                step = w//4
                rows = [int(data[i:i+step],16) for i in range(0,len(data),step)]
                self.glyphs[cp] = Glyph(w,16,0,0,w,rows)

    def render(self, char, width=None, height=None):
        cp = ord(char)
        if cp not in self.glyphs: raise ValueError(f'Missing glyph U+{cp:04X} {char!r}.')
        glyph = self.glyphs[cp]
        width, height = width or self.width, height or self.height
        out = [[0]*width for _ in range(height)]
        top = self.ascent - glyph.y_offset - glyph.height
        for y,row in enumerate(glyph.rows):
            for x in range(glyph.width):
                if row & (1 << (glyph.width-1-x)):
                    xx,yy = x+glyph.x_offset,y+top
                    if not (0 <= xx < width and 0 <= yy < height):
                        raise ValueError(f'U+{cp:04X} does not fit {width}x{height}; refusing to clip strokes.')
                    out[yy][xx] = 1
        return out

def text_chars(path=None, text=None):
    value = Path(path).read_text(encoding='utf-8-sig') if path else text
    if value is None: raise ValueError('Supply --chars-file or --text.')
    chars = list(dict.fromkeys(c for c in value if c not in '\r\n\t'))
    if not chars: raise ValueError('Character list is empty.')
    if any(ord(c)<32 or ord(c)==127 for c in chars): raise ValueError('Unexpected control code in character list.')
    return chars

def coverage(font, chars):
    missing = [dict(char=c,unicode=f'U+{ord(c):04X}') for c in chars if ord(c) not in font.glyphs]
    return dict(ok=not missing,requested=len(chars),present=len(chars)-len(missing),missing=missing)

def pack_pixels(pixels, fmt, ink=1):
    height,width = len(pixels),len(pixels[0]); out=bytearray()
    if fmt=='mono1':
        for row in pixels:
            for x in range(0,width,8):
                out.append(sum((row[x+i] if x+i<width else 0) << (7-i) for i in range(8)))
    else:
        if width%8 or height%8: raise ValueError('Tile output width and height must be multiples of 8.')
        if not 1 <= ink <= (3 if fmt=='gb2' else 15): raise ValueError('Foreground index out of range.')
        for ty in range(0,height,8):
            for tx in range(0,width,8):
                for y in range(8):
                    row=pixels[ty+y][tx:tx+8]
                    if fmt=='gb2':
                        for bit in (0,1): out.append(sum((p*((ink>>bit)&1)) << (7-x) for x,p in enumerate(row)))
                    elif fmt=='gba4':
                        for x in range(0,8,2): out.append(row[x]*ink | (row[x+1]*ink << 4))
                    else: raise ValueError('Unknown format.')
    return bytes(out)

def png_bytes(pixels, scale=1):
    height,width=len(pixels),len(pixels[0])
    def chunk(tag,data): return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    rows=[]
    for row in pixels:
        expanded=bytes(0 if p else 255 for p in row for _ in range(scale))
        rows.extend([b'\0'+expanded]*scale)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width*scale,height*scale,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')

def write_new(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(data)

def preview(font,chars,path,scale=4,columns=16):
    w,h=font.width,font.height;gap=2;columns=min(columns,len(chars))
    rows=(len(chars)+columns-1)//columns
    pixels=[[0]*(columns*(w+gap)+gap) for _ in range(rows*(h+gap)+gap)]
    for i,char in enumerate(chars):
        image=font.render(char);ox=gap+(i%columns)*(w+gap);oy=gap+(i//columns)*(h+gap)
        for y,line in enumerate(image): pixels[oy+y][ox:ox+w]=line
    write_new(path,png_bytes(pixels,scale))

def export(font,chars,directory,fmt,width=None,height=None,ink=1):
    check=coverage(font,chars)
    if not check['ok']:raise ValueError('Missing glyphs; run check for the exact list.')
    width,height=width or font.width,height or font.height
    if fmt!='mono1':width=(width+7)//8*8;height=(height+7)//8*8
    payload=bytearray();records=[]
    for i,char in enumerate(chars):
        glyph=font.glyphs[ord(char)];pixels=font.render(char,width,height)
        raw=pack_pixels(pixels,fmt,ink)
        records.append(dict(slot=i,char=char,unicode=f'U+{ord(char):04X}',offset=len(payload),bytes=len(raw),
                            source_advance=glyph.advance,source_bbx=[glyph.width,glyph.height,glyph.x_offset,glyph.y_offset]))
        payload.extend(raw)
    result=dict(format=fmt,cell_width=width,cell_height=height,ink_index=1 if fmt=='mono1' else ink,
                glyph_count=len(chars),source_font=font.path.name,source_sha256=hashlib.sha256(font.path.read_bytes()).hexdigest(),
                output_sha256=hashlib.sha256(payload).hexdigest(),glyphs=records,
                warning='Slots are NOT game character codes. This is font data, not a ROM patch. Retain the source font license and credits.')
    directory=Path(directory)
    if directory.exists():raise FileExistsError('Output directory already exists; use a new directory.')
    directory.mkdir(parents=True,exist_ok=False)
    write_new(directory/'glyphs.bin',payload)
    write_new(directory/'glyphs.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    tsv='slot\tunicode\tcharacter\tbyte_offset\tbyte_length\tsource_advance\n'+''.join(f"{g['slot']}\t{g['unicode']}\t{g['char']}\t{g['offset']}\t{g['bytes']}\t{g['source_advance']}\n" for g in records)
    write_new(directory/'unicode_to_slot.tsv',tsv.encode('utf-8-sig'))
    write_new(directory/'LICENSE_REMINDER.txt',b'Font-derived data. Retain original font license and copyright notices with any redistribution.\n')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('catalog')
    sub.add_parser('verify-assets')
    for command in ['check','preview','export']:
        p=sub.add_parser(command);p.add_argument('--font',required=True,type=Path)
        group=p.add_mutually_exclusive_group(required=True);group.add_argument('--chars-file',type=Path);group.add_argument('--text')
        if command=='preview':p.add_argument('--output',type=Path,required=True);p.add_argument('--scale',type=int,default=4,choices=range(1,17));p.add_argument('--columns',type=int,default=16,choices=range(1,65))
        if command=='export':
            p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--format',choices=['mono1','gb2','gba4'],required=True)
            p.add_argument('--width',type=int,choices=range(1,129));p.add_argument('--height',type=int,choices=range(1,129));p.add_argument('--ink',type=int,default=1)
    args=parser.parse_args()
    try:
        if args.command=='catalog':result=json.loads((ROOT/'fonts/FONT_CATALOG.json').read_text(encoding='utf-8'))
        elif args.command=='verify-assets':
            manifest=json.loads((ROOT/'fonts/FONT_MANIFEST.json').read_text(encoding='utf-8'))
            failed=[]
            for item in manifest['files']:
                p=ROOT/item['path']
                if not p.is_file() or p.stat().st_size!=item['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
                    failed.append(item['path'])
            result=dict(ok=not failed,checked=len(manifest['files']),failures=failed)
        else:
            font=Font(args.font);chars=text_chars(args.chars_file,args.text);result=coverage(font,chars)
            if args.command=='check':result.update(font=font.path.name,total_font_glyphs=len(font.glyphs),nominal_cell=[font.width,font.height])
            elif not result['ok']:raise ValueError('Missing glyphs: '+json.dumps(result['missing'],ensure_ascii=False))
            elif args.command=='preview':preview(font,chars,args.output,args.scale,args.columns);result['preview']=str(args.output)
            else:result=export(font,chars,args.output_dir,args.format,args.width,args.height,args.ink)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('ok',True) else 2
    except Exception as exc:print(f'ERROR: {exc}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
