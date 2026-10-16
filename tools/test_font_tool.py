"""Windows-compatible tests for actual fonts, layout, bit order, and output protection."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parent))
from font_tool import Font, coverage, export, pack_pixels, preview, png_bytes

ROOT=Path(__file__).resolve().parents[1]

def decode(raw,width,height,fmt):
    result=[]
    for y in range(height):
        line=[]
        for x in range(width):
            if fmt=='mono1':
                value=raw[y*((width+7)//8)+x//8] >> (7-x%8) & 1
            else:
                tile=(y//8)*(width//8)+x//8
                if fmt=='gb2':
                    pos=tile*16+(y%8)*2
                    value=(raw[pos]>>(7-x%8)&1)|((raw[pos+1]>>(7-x%8)&1)<<1)
                else:
                    pos=tile*32+(y%8)*4+(x%8)//2
                    value=raw[pos]>>((x%2)*4)&15
            line.append(1 if value else 0)
        result.append(line)
    return result

def must_fail(function):
    try:function()
    except (ValueError,FileExistsError):return
    raise AssertionError('Invalid operation was accepted.')

def main():
    report={'ok':False,'scope':'Font assets and conversion only; no ROM injection or game-layout acceptance','checks':{}}
    try:
        with tempfile.TemporaryDirectory(prefix='ROMFontTest_') as td:
            base=Path(td)
            fixture=base/'fixture.bdf'
            fixture.write_text('''STARTFONT 2.1
FONTBOUNDINGBOX 8 8 0 0
FONT_ASCENT 8
STARTCHAR test
ENCODING 65
DWIDTH 6 0
BBX 3 3 2 1
BITMAP
A0
40
E0
ENDCHAR
STARTCHAR space
ENCODING 32
DWIDTH 4 0
BBX 0 0 0 0
BITMAP
ENDCHAR
ENDFONT
''',encoding='ascii')
            f=Font(fixture);image=f.render('A')
            expected={(2,4),(4,4),(3,5),(2,6),(3,6),(4,6)}
            assert {(x,y) for y,row in enumerate(image) for x,p in enumerate(row) if p}==expected
            assert all(p==0 for row in f.render(' ') for p in row)
            must_fail(lambda:f.render('A',4,8))
            pix=[[0]*8 for _ in range(8)];pix[0][0]=pix[0][7]=pix[1][1]=1
            assert pack_pixels(pix,'mono1')[:2]==b'\x81\x40'
            assert pack_pixels(pix,'gb2')[:4]==b'\x81\x00\x40\x00'
            assert pack_pixels(pix,'gb2',3)[:4]==b'\x81\x81\x40\x40'
            assert pack_pixels(pix,'gba4')[:8]==b'\x01\x00\x00\x10\x10\x00\x00\x00'
            must_fail(lambda:pack_pixels(pix,'gb2',4))
            report['checks']['known_bit_order_and_bdf_offsets']=True
            chars=list('汉化测试字体游戏开始保存读取装备攻击防御道具勇者爱龙，。！？0123456789ABC')
            report['checks']['fonts']=[]
            for path in sorted((ROOT/'fonts').rglob('*')):
                if path.suffix.lower() not in ('.bdf','.hex'):continue
                font=Font(path);check=coverage(font,chars);assert check['ok'],check
                before=hashlib.sha256(path.read_bytes()).hexdigest()
                record={'font':path.name,'glyph_count':len(font.glyphs),'nominal_cell':[font.width,font.height],
                        'sample_count':len(chars),'formats':{}}
                for fmt in ('mono1','gb2','gba4'):
                    target=base/(path.stem+'_'+fmt)
                    manifest=export(font,chars,target,fmt)
                    raw=(target/'glyphs.bin').read_bytes()
                    for glyph in manifest['glyphs']:
                        chunk=raw[glyph['offset']:glyph['offset']+glyph['bytes']]
                        actual=decode(chunk,manifest['cell_width'],manifest['cell_height'],fmt)
                        assert actual==font.render(glyph['char'],manifest['cell_width'],manifest['cell_height'])
                    record['formats'][fmt]={'cell':[manifest['cell_width'],manifest['cell_height']],'roundtrip_passed':True,'bytes':len(raw)}
                    must_fail(lambda:export(font,chars,target,fmt))
                missing=base/(path.stem+'_missing')
                must_fail(lambda:export(font,[chr(0x10ffff)],missing,'mono1'))
                assert not missing.exists()
                png=base/(path.stem+'.png');preview(font,chars,png)
                assert png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
                assert hashlib.sha256(path.read_bytes()).hexdigest()==before
                record.update(source_unchanged=True,missing_glyph_rejected=True,overwrite_rejected=True)
                report['checks']['fonts'].append(record)
            assert len(report['checks']['fonts'])==len(json.loads((ROOT/'fonts/FONT_CATALOG.json').read_text(encoding='utf-8'))['fonts'])
            # Verify PNG pixel rows independently of the font renderer.
            png=png_bytes(pix,2);pos=8;compressed=b''
            while pos<len(png):
                length=struct.unpack_from('>I',png,pos)[0];kind=png[pos+4:pos+8];data=png[pos+8:pos+8+length]
                assert zlib.crc32(kind+data)&0xffffffff==struct.unpack_from('>I',png,pos+8+length)[0]
                if kind==b'IDAT':compressed+=data
                pos+=12+length
            rows=zlib.decompress(compressed)
            assert rows[:17]==b'\0'+b'\0\0'+bytes([255])*12+b'\0\0'
            report['checks']['png_crc_and_pixel_rows']=True
            probe=subprocess.run([sys.executable,str(ROOT/'tools/font_tool.py'),'check','--font',str(fixture),'--text','AB'],capture_output=True,text=True,encoding='utf-8')
            assert probe.returncode==2 and json.loads(probe.stdout)['missing']==[{'char':'B','unicode':'U+0042'}]
            report['checks']['cli_missing_glyph_exit_2']=True
        report['ok']=True
    except Exception as exc:
        report['error']=repr(exc)
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
