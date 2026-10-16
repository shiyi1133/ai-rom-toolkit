"""Rebuild a no-clipping cell-sized BDF subset from a Bits'n'Picas KBITX font.

Source and original TTF remain unchanged. No third-party modules are required.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import xml.etree.ElementTree as ET

def decode_bitmap(encoded):
    data=base64.b64decode(encoded+'='*((-len(encoded))%4),validate=True)
    if len(data)<2:raise ValueError('Missing bitmap dimensions.')
    height,width=data[:2];position=2;pixels=[]
    while position<len(data):
        operation=data[position];position+=1
        count=(operation&31)*(32 if operation&32 else 1)
        mode=operation>>6
        if count==0:raise ValueError('Invalid zero-length bitmap run.')
        if mode==0:pixels.extend([0]*count)
        elif mode==1:pixels.extend([255]*count)
        elif mode==2:
            if position>=len(data):raise ValueError('Truncated repeated value.')
            pixels.extend([data[position]]*count);position+=1
        else:
            if position+count>len(data):raise ValueError('Truncated literal run.')
            pixels.extend(data[position:position+count]);position+=count
        if len(pixels)>width*height:raise ValueError('Bitmap exceeds declared dimensions.')
    if len(pixels)!=width*height or not set(pixels).issubset({0,255}):
        raise ValueError('Expected an exact monochrome bitmap.')
    return width,height,[pixels[y*width:(y+1)*width] for y in range(height)]

def convert(source,output,excluded_output,width=8,height=12,ascent=10):
    if output.exists() or excluded_output.exists():raise FileExistsError('Output already exists; choose new filenames.')
    root=ET.parse(source).getroot();glyphs=[];excluded=[];seen=set()
    copyright_text=next((n.get('value','') for n in root.findall('name') if n.get('id')=='0'),'See source font copyright metadata.')
    for element in root.findall('g'):
        a=element.attrib
        if 'u' not in a:continue
        cp=int(a['u'])
        if cp in seen or not 0<=cp<=0x10ffff:raise ValueError('Invalid or duplicate Unicode encoding.')
        seen.add(cp)
        w,h,rows=decode_bitmap(a['d'])
        x,top,advance=int(a['x']),int(a['y']),int(a['w'])
        record=dict(cp=cp,width=w,height=h,x=x,top=top,advance=advance)
        if not(0<=x and x+w<=width and top<=ascent and top-h>=ascent-height and advance<=width):
            excluded.append(record);continue
        record['rows']=rows;glyphs.append(record)
    family='ROM Toolkit 400 Grid12'
    lines=['STARTFONT 2.1','COMMENT Derived convenience subset of user-supplied 400.ttf; source retained unchanged.',
      'COMMENT Modified format/subset name: ROM Toolkit 400 Grid12. Licensed under SIL OFL 1.1.',
      'FONT -ROMToolkit-ROM Toolkit 400 Grid12-Medium-R-Normal--12-120-75-75-C-80-ISO10646-1','SIZE 12 75 75',
      f'FONTBOUNDINGBOX {width} {height} 0 {ascent-height}','STARTPROPERTIES 7',f'FAMILY_NAME "{family}"',
      f'FONT_ASCENT {ascent}',f'FONT_DESCENT {height-ascent}',f'PIXEL_SIZE {height}',
      'COPYRIGHT '+json.dumps(copyright_text,ensure_ascii=True),'FONT_VERSION "400.ttf native grid subset 2026-10-16"',
      'DEFAULT_CHAR 32','ENDPROPERTIES',f'CHARS {len(glyphs)}']
    for g in glyphs:
        w,h=g['width'],g['height'];stride=(w+7)//8
        lines.extend([f"STARTCHAR uni{g['cp']:04X}",f"ENCODING {g['cp']}",f"SWIDTH {g['advance']*1000//height} 0",
          f"DWIDTH {g['advance']} 0",f"BBX {w} {h} {g['x']} {g['top']-h}",'BITMAP'])
        for row in g['rows']:
            bits=0
            for pixel in row:bits=(bits<<1)|(1 if pixel else 0)
            lines.append(f'{bits << (stride*8-w):0{stride*2}X}')
        lines.append('ENDCHAR')
    lines.append('ENDFONT')
    output.parent.mkdir(parents=True,exist_ok=True);excluded_output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='ascii',newline='\n') as f:f.write('\n'.join(lines)+'\n')
    note='These original glyphs remain in 400.ttf and the upstream source. They are excluded only from the 8x12 convenience BDF because of overhang, height, or advance; nothing is cropped.'
    with excluded_output.open('x',encoding='utf-8') as f:json.dump(dict(note=note,glyphs=excluded),f,ensure_ascii=False,indent=2)
    return dict(glyphs=len(glyphs),excluded=len(excluded),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
      output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),cell=[width,height],derived_family=family)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--excluded',type=Path,required=True);args=parser.parse_args()
    result=convert(args.source,args.output,args.excluded)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
