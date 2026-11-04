"""Content-only packaging of ViSe's verified web archive, never activation.

The protected caller supplies the digest from the verified signed attestation.
No archive path is passed to an extraction API or executed.
"""
import hashlib,io,tarfile
from pathlib import PurePosixPath

LIMIT=64*1024**2

def require(value):
    if not value:raise ValueError('VISE_PACKAGE_CONTENT_REFUSED')

def frontend(raw,expected):
    require(type(raw) is bytes and 0<len(raw)<=LIMIT
            and hashlib.sha256(raw).hexdigest()==expected)
    files={};total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive:
            name=member.name;path=PurePosixPath(name)
            require(len(files)<4096 and member.isfile() and not member.issparse()
                and not member.pax_headers and not member.linkname
                and member.mode==0o444 and member.uid==member.gid==member.mtime==0
                and member.uname==member.gname=='' and 0<=member.size<=LIMIT
                and 0<len(name)<=1024 and str(path)==name and not path.is_absolute()
                and all(p not in {'','.','..'} for p in name.split('/'))
                and '\\' not in name and all(ord(c)>=32 and ord(c)!=127 for c in name)
                and name not in files)
            total+=member.size;require(total<=LIMIT)
            data=archive.extractfile(member).read(member.size+1)
            require(len(data)==member.size);files[name]=data
    require('index.html' in files and files['index.html'])
    require(all(str(parent) not in files for name in files
                for parent in PurePosixPath(name).parents if str(parent)!='.'))
    # The verifier emits sorted USTAR files with fixed metadata. Reconstructing
    # this format also rejects hidden trailing members, padding and extensions.
    canonical=io.BytesIO()
    with tarfile.open(fileobj=canonical,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o444;member.mtime=0
            archive.addfile(member,io.BytesIO(data))
    require(canonical.getvalue()==raw)
    return files
