"""Verify recorded package files; user-generated workspace outputs are ignored."""
from pathlib import Path
import hashlib
import json
ROOT=Path(__file__).resolve().parents[1]

def main():
    manifest=json.loads((ROOT/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    failures=[]
    for item in manifest['files']:
        p=ROOT/item['path']
        if not p.is_file():failures.append(dict(path=item['path'],reason='missing'));continue
        with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=item['sha256'] or p.stat().st_size!=item['bytes']:
            failures.append(dict(path=item['path'],reason='size or SHA-256 mismatch'))
    print(json.dumps(dict(ok=not failures,checked=len(manifest['files']),failures=failures),indent=2))
    return 0 if not failures else 1

if __name__=='__main__':raise SystemExit(main())
