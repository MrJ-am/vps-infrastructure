"""One immutable reviewed source overlay, before any candidate execution."""
import os,stat,subprocess
from pathlib import Path
import base_policy as original
from sandbox import require

CONTRACT=original.read_json(Path('@contract@'),16384)
PATCH=Path('@patch@')
PATCH_TOOL='@patch-tool@'
STEP='rust-reviewed-readiness-overlay'

def checked(value):
    # The only supported object consists of fixed strings and fixed file lists;
    # equality also rejects missing/extra fields or another patch/base/result.
    require(type(value) is dict and value==CONTRACT,'READINESS_OVERLAY_POLICY_REFUSED')
    return value

def inventory(directory):
    require(directory.is_dir() and not directory.is_symlink(),'READINESS_SOURCE_DIRECTORY_REFUSED')
    result={};total=0;objects=0
    for path in directory.rglob('*'):
        objects+=1;require(objects<=16384,'READINESS_SOURCE_LIMIT')
        entry=path.lstat()
        require(stat.S_ISDIR(entry.st_mode) or stat.S_ISREG(entry.st_mode),'READINESS_SOURCE_TYPE_REFUSED')
        if stat.S_ISDIR(entry.st_mode):continue
        require(entry.st_nlink==1 and entry.st_uid==os.getuid(),'READINESS_SOURCE_METADATA_REFUSED')
        total+=entry.st_size
        require(len(result)<4096 and total<=32*1024*1024,'READINESS_SOURCE_LIMIT')
        result[str(path.relative_to(directory))]={'bytes':entry.st_size,'sha256':original.sha(path)}
    return result

def apply(directory,policy):
    checked(policy.get('readiness_overlay'))
    require(next((item['revision'] for item in policy['sources'] if item['id']=='platform'),None)==CONTRACT['base_platform_revision'],'READINESS_BASE_REVISION_REFUSED')
    require(PATCH.is_file() and not PATCH.is_symlink() and PATCH.stat().st_size<=65536
        and original.sha(PATCH)==CONTRACT['patch_sha256'],'READINESS_PATCH_HASH_REFUSED')
    before=inventory(directory)
    changed={item['path']:item for item in CONTRACT['files']}
    require(set(changed)=={'crates/server/src/database.rs','crates/server/tests/runtime_postgres.rs'},'READINESS_TARGET_SET_REFUSED')
    for name,item in changed.items():require(name in before and before[name]['sha256']==item['base_sha256'],'READINESS_BASE_CONTENT_REFUSED')
    result=subprocess.run([PATCH_TOOL,'--fuzz=0','--batch','--forward','--no-backup-if-mismatch','--reject-file=-','-p1','-i',str(PATCH)],
        cwd=directory,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        env={'LANG':'C','LC_ALL':'C','PATH':'/nonexistent'},timeout=10,check=False)
    require(result.returncode==0,'READINESS_PATCH_APPLY_REFUSED')
    after=inventory(directory)
    require(set(after)==set(before),'READINESS_FILE_SET_CHANGED')
    for name,item in before.items():
        require(after[name]['sha256']==changed[name]['compiled_sha256'] if name in changed else after[name]==item,'READINESS_COMPILED_CONTENT_REFUSED')
    return STEP
