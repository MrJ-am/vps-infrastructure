#!/usr/bin/env python3
"""Read-only diagnosis of the two fixed retained archive-adoption images.

Private bytes remain inside this process. No value, key, count, SQL definition,
digest, exception, file listing, network access or application journal is emitted.
Only immutable qualified reader functions are reused; publish/main are not called.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

MODULE=Path('/nix/store/8x4pybgyhkz01jqd41363wfs5rz0fm8i-mrjam-mail-native-adoption-3/libexec/adopt-archive.py')
MODULE_HASH='ccbef53836806be24f41e46e27ec46bda46f19a62ae19021f82e5e9564ae456b'
STAGING=Path('/run/mrjam-archive-mail-adoption')
RETAINED=Path('/var/lib/mrjam-cutover/first-deployment/snapshot/candidate-state-retained/mrjam-vision-archive')
CURRENT=Path('/var/lib/mrjam-vision-archive')
SOURCE_NAMES={'closure':'closure.sqlite','global':'global.sqlite'}


class ClosedFailure(Exception):
    pass


def metadata(path,uid,gid,mode,maximum=None,directory=False):
    try:item=path.lstat()
    except FileNotFoundError:return {'present':False,'expected_metadata':False}
    valid=(stat.S_ISDIR(item.st_mode) if directory else stat.S_ISREG(item.st_mode))
    valid=valid and item.st_uid==uid and item.st_gid==gid and stat.S_IMODE(item.st_mode)==mode
    if not directory:valid=valid and item.st_nlink in (1,2) and 100<=item.st_size<=maximum
    return {'present':True,'expected_metadata':bool(valid),
            **({} if directory else {'single_link':item.st_nlink==1,'two_links':item.st_nlink==2})}


def load_module():
    if hashlib.sha256(MODULE.read_bytes()).hexdigest()!=MODULE_HASH:raise ClosedFailure('ADOPTER_BINDING_REFUSED')
    spec=importlib.util.spec_from_file_location('closed_archive_adopter',MODULE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def read_fixed(module,parent,name,maximum,uid,gid,mode):
    # Every ancestor must be a directory, never a symlink. Contents are never
    # opened from the restored live legacy databases or secret references.
    for directory in reversed((parent,)+tuple(parent.parents)):
        if not stat.S_ISDIR(directory.lstat().st_mode):raise ClosedFailure('IMAGE_PATH_REFUSED')
    fd=os.open(parent/name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        item=os.fstat(fd)
        if item.st_uid!=uid or item.st_gid!=gid or stat.S_IMODE(item.st_mode)!=mode or item.st_nlink not in (1,2):
            raise ClosedFailure('IMAGE_METADATA_CHANGED')
        return module.read_fd(fd,maximum)
    finally:os.close(fd)


def schema_shape(module,raw,scope):
    """Only compatibility booleans, never actual object or column names."""
    try:db=module.connection(raw)
    except Exception:return {'sqlite_header_accepted':False}
    try:
        actual=module.objects(db)
        columns=db.execute('PRAGMA table_info(courriels)').fetchall()
        names=[row[:3] for row in actual]
        exact=shape=layout=False
        for native in (False,True):
            for hashes in (0,1,2):
                for marker in ((None,scope) if scope in module.MARKERS else (None,)):
                    model=module.reference(native=native,hashes=hashes,marker=marker)
                    try:
                        expected=module.objects(model)
                        exact=exact or actual==expected
                        shape=shape or names==[row[:3] for row in expected]
                        layout=layout or columns==model.execute('PRAGMA table_info(courriels)').fetchall()
                    finally:model.close()
        integrity=db.execute('PRAGMA integrity_check(1)').fetchone()==('ok',)
        return {'sqlite_header_accepted':True,'exact_schema_accepted':exact,
                'object_identities_compatible':shape,'mail_column_layout_compatible':layout,
                'integrity_accepted':integrity}
    except Exception:return {'sqlite_header_accepted':True,'schema_observation_available':False}
    finally:db.close()


def classify_sources(module,raws):
    shapes={scope:schema_shape(module,raws[scope],scope) for scope in SOURCE_NAMES}
    copied={}
    for scope in SOURCE_NAMES:
        try:db=module.inspect(raws[scope],scope=scope)
        except Exception:return {'code':scope.upper()+'_SCHEMA_OR_INTEGRITY_REFUSED','shapes':shapes},None
        try:
            try:
                names,rows=module.rows(db)
                canonical=[module.canonical_row(names,row) for row in rows]
            except Exception:return {'code':scope.upper()+'_ROW_CONTRACT_REFUSED','shapes':shapes},None
            try:module.marker_rows(db,scope)
            except Exception:return {'code':scope.upper()+'_MARKER_CONTRACT_REFUSED','shapes':shapes},None
            for row in canonical:
                key=row[0]
                if key in copied and copied[key]!=row:
                    return {'code':'MAIL_KEY_CONFLICT','shapes':shapes},None
                copied[key]=row
                if len(copied)>module.MAX_ROWS:
                    return {'code':'MERGED_ROW_LIMIT_REFUSED','shapes':shapes},None
        finally:db.close()
    try:merged=module.merge(raws['closure'],raws['global'],profile='archive')
    except Exception:return {'code':'MERGE_OTHER_BOUND_OR_CONTRACT_REFUSED','shapes':shapes},None
    return {'code':'SOURCE_MERGE_ACCEPTED','shapes':shapes},merged


def classify_target(module,merged,metadata_result,reader):
    if not metadata_result['directory']['present']:return {'code':'RETAINED_TARGET_DIRECTORY_ABSENT'}
    if not metadata_result['directory']['expected_metadata']:return {'code':'RETAINED_TARGET_DIRECTORY_METADATA_REFUSED'}
    for name in ('installed','pending'):
        item=metadata_result[name]
        if not item['present']:continue
        if not item['expected_metadata']:return {'code':name.upper()+'_TARGET_METADATA_REFUSED'}
        try:raw=reader(name)
        except Exception:return {'code':name.upper()+'_TARGET_READ_REFUSED'}
        try:equivalent=module.equivalent(raw,merged)
        except Exception:return {'code':name.upper()+'_TARGET_SCHEMA_REFUSED'}
        if not equivalent:return {'code':name.upper()+'_TARGET_DIFFERENT'}
    if metadata_result['installed']['present'] and metadata_result['pending']['present']:
        return {'code':'BOTH_TARGET_NAMES_REQUIRE_SAME_INODE_CHECK'}
    return {'code':'TARGET_PUBLICATION_PRECONDITIONS_ACCEPTED',
            'publication_io_success_proved':False,'unit_readonly_mount_reobserved':False}


def collect():
    module=load_module()
    observed={'staging_directory':metadata(STAGING,943,943,0o700,directory=True),
              'source_images':{scope:metadata(STAGING/name,0,943,0o440,module.MAX_SOURCE) for scope,name in SOURCE_NAMES.items()},
              'retained_target':{'directory':metadata(RETAINED,943,943,0o700,directory=True),
                'installed':metadata(RETAINED/module.DESTINATION,943,943,0o600,module.MAX_TARGET),
                'pending':metadata(RETAINED/module.PENDING,943,943,0o600,module.MAX_TARGET)},
              'restored_live_directory':metadata(CURRENT,943,943,0o700,directory=True)}
    value={'schema_version':1,'code':'ARCHIVE_DIAGNOSIS_OBSERVED','metadata':observed,
           'source_content_read_locally':False,'private_values_exported':False,
           'secret_content_read':False,'journals_read':False,'mutation_performed':False}
    if not observed['staging_directory']['expected_metadata'] or not all(
            item['expected_metadata'] and item['single_link'] for item in observed['source_images'].values()):
        value['classification']={'code':'SOURCE_METADATA_REFUSED_OR_ABSENT'}
        return value
    raws={scope:read_fixed(module,STAGING,name,module.MAX_SOURCE,0,943,0o440) for scope,name in SOURCE_NAMES.items()}
    value['source_content_read_locally']=True
    diagnosis,merged=classify_sources(module,raws)
    value['classification']=diagnosis
    if merged is not None:
        filenames={'installed':module.DESTINATION,'pending':module.PENDING}
        value['target_classification']=classify_target(module,merged,observed['retained_target'],
            lambda name:read_fixed(module,RETAINED,filenames[name],module.MAX_TARGET,943,943,0o600))
    return value


def main():
    if len(sys.argv)!=1 or os.geteuid()!=0:return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
    signal.alarm(60)
    try:value=collect();code=0
    except Exception:value={'schema_version':1,'code':'ARCHIVE_DIAGNOSIS_UNAVAILABLE','private_values_exported':False,'mutation_performed':False};code=1
    finally:signal.alarm(0)
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return code


if __name__=='__main__':raise SystemExit(main())
