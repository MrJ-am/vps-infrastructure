"""Bind proposed code to the installed offline dependency materialization.

Changing dependencies requires a new verified materialization. A candidate
cannot replace this directory, fetch a package or run an install lifecycle.
"""
import os,re,stat
from pathlib import Path
import source_policy as P

MATERIALIZATION='b0c8a52571c4e1c3b89b5c72b82f15a55bb968d4d1a1a95ca3c433c9ef2b651f'
LOCKS={'backend/Cargo.lock','package-lock.json','elm.json'}
NPM_FIELDS={'dependencies','devDependencies','optionalDependencies','peerDependencies',
    'peerDependenciesMeta','overrides','workspaces','os','cpu'}

def verify(source,dependencies,*,isolated=False):
    source=Path(source);dependencies=Path(dependencies)
    P.require(re.fullmatch('/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+',str(dependencies))
        and dependencies.resolve()==dependencies,'VISE_DEPENDENCY_STORE_REFUSED')
    owner=0
    if isolated:
        # In the worker's single-UID namespace host root is unmapped. The
        # protected worker pins the store closure before mounting it readonly.
        mapping=Path('/proc/self/uid_map').read_text().split()
        P.require(len(mapping)==3 and mapping[0]==str(os.getuid()) and mapping[2]=='1'
            and os.getuid()!=0 and os.statvfs(dependencies).f_flag&os.ST_RDONLY,
            'VISE_DEPENDENCY_NAMESPACE_REFUSED')
        owner=int(Path('/proc/sys/kernel/overflowuid').read_text())
    meta=dependencies.lstat()
    P.require(stat.S_ISDIR(meta.st_mode) and meta.st_uid==owner and not meta.st_mode&0o222,'VISE_DEPENDENCY_METADATA_REFUSED')
    value=P.read_json(dependencies/'descriptor.json')
    P.exact(value,{'schema_version','materialization_sha256','locks','npm_dependency_fields','npm_lifecycle_scripts'})
    P.require(type(value['schema_version']) is int and value['schema_version']==1
        and value['materialization_sha256']==MATERIALIZATION and value['npm_lifecycle_scripts'] is False,
        'VISE_DEPENDENCY_MATERIALIZATION_REFUSED')
    P.require(type(value['locks']) is dict and set(value['locks'])==LOCKS,'VISE_DEPENDENCY_LOCK_SET_REFUSED')
    for name,digest in value['locks'].items():
        P.require(type(digest) is str and P.HEX64.fullmatch(digest) and P.sha(source/name)==digest,
            'VISE_DEPENDENCY_REFRESH_REQUIRED')
    package=P.read_json(source/'package.json')
    P.require(type(package) is dict and type(value['npm_dependency_fields']) is dict
        and set(value['npm_dependency_fields'])<=NPM_FIELDS
        and {k:package[k] for k in NPM_FIELDS if k in package}==value['npm_dependency_fields'],
        'VISE_DEPENDENCY_REFRESH_REQUIRED')
    for name in ['cargo-vendor','node_modules','elm-home']:
        info=(dependencies/name).lstat()
        P.require(stat.S_ISDIR(info.st_mode) and info.st_uid==owner and not info.st_mode&0o222,
            'VISE_DEPENDENCY_METADATA_REFUSED')
    return value
