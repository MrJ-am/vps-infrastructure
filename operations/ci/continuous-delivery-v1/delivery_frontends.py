"""Validate signed frontend archive bytes without extracting archive paths.

The caller supplies bindings from the verified admission/attestation. This
parser grants no release authority and invokes no candidate code.
"""
import hashlib
import io
import json
from pathlib import PurePosixPath
import tarfile

NAMES=frozenset(('audition','log','logique','mateval','vision','style','style-logo'))
MAX_BYTES=64*1024*1024
FIELDS={'schema_version','artifact','deployment_authorized','input_manifest_sha256',
        'runtime_qualification','source_commits','style_revision','toolchains_lock_sha256',
        'payload_sha256'}


def require(value):
    if not value:raise ValueError('FRONTEND_DELIVERY_REFUSED')


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result);result[key]=value
    return result


def digest(raw):return hashlib.sha256(raw).hexdigest()


def validate(raw, *, archive_sha256, proposal, sources, styles, toolchains_sha256):
    require(type(raw) is bytes and 0<len(raw)<=MAX_BYTES and digest(raw)==archive_sha256)
    require(set(styles)==NAMES)
    files={name:{} for name in NAMES};total=0;count=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive:
            count+=1;require(count<=16384)
            name=member.name;path=PurePosixPath(name)
            require(member.isfile() and not member.issparse() and member.mode==0o444
                    and member.mtime==0 and member.uid==member.gid==0
                    and 0<=member.size<=MAX_BYTES and len(name)<=1024
                    and str(path)==name and not path.is_absolute() and '..' not in path.parts
                    and '\\' not in name and all(ord(c)>=32 and ord(c)!=127 for c in name)
                    and len(path.parts)>=2 and path.parts[0] in NAMES)
            total+=member.size;require(total<=MAX_BYTES)
            group=path.parts[0];relative='/'.join(path.parts[1:])
            require(relative not in files[group])
            data=archive.extractfile(member).read(member.size+1)
            require(len(data)==member.size)
            files[group][relative]=data
    for group,items in files.items():
        require('artifact.json' in items and len(items)>1 and len(items['artifact.json'])<=131072)
        metadata=json.loads(items['artifact.json'],object_pairs_hook=unique)
        require(type(metadata) is dict and set(metadata)==FIELDS
                and type(metadata['schema_version']) is int and metadata['schema_version']==1
                and metadata['artifact']==group+'-elm'
                and metadata['deployment_authorized'] is False
                and metadata['runtime_qualification']=='local-verifier-content-only'
                and metadata['input_manifest_sha256']==proposal
                and metadata['source_commits']==sources
                and metadata['style_revision']==styles[group]
                and metadata['toolchains_lock_sha256']==toolchains_sha256
                and metadata['payload_sha256']=={name:digest(data) for name,data in items.items() if name!='artifact.json'})
        # A file must not also be a parent directory of another archive entry.
        require(all(str(parent) not in items for name in items for parent in PurePosixPath(name).parents if str(parent)!='.'))
    return files
