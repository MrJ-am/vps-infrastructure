"""Assemble only the three exact code selections from the received proposal."""
import hashlib
import json
from pathlib import Path
import sys

def main():
    if len(sys.argv)!=3:raise ValueError()
    base=Path(sys.argv[1]);out=Path(sys.argv[2])
    raw=(base/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='8bf05fb9065a4c91e565ec0d37f24f2c556f315109823ccdef95c6354b423d6a':raise ValueError()
    manifest=json.loads(raw)
    expected={f['path'] for f in manifest['files']}
    actual={str(p.relative_to(base)) for p in base.rglob('*') if p.is_file()}
    if actual!=expected|{'manifest.json'}:raise ValueError()
    for item in manifest['files']:
        path=base/item['path']
        if path.is_symlink() or '..' in path.parts:raise ValueError()
        data=path.read_bytes()
        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError()
    out.mkdir()
    for name,prefix in [('platform',''),('vision','components/vision/'),('mateval','components/mateval/')]:
        root=base/'sources'/name
        for source in root.rglob('*'):
            if source.is_file():
                target=out/(prefix+str(source.relative_to(root)))
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())

if __name__=='__main__':main()
