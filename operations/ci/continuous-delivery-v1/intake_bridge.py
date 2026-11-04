"""Bounded metadata exchange between intake and the protected controller.

The intake exports untrusted ready metadata. Only exact root-owned decisions
can acknowledge a result or request re-preparation. Neither operation authorizes
CI or deployment. SQLite is opened only by its own intake principal.
"""
import json,os,re,shutil,stat
from pathlib import Path
import intake_queue as Q
import intake_prepare as W
from proposal_prepare import encode,sha

HEX=re.compile('[0-9a-f]{64}\\Z')
def require(value,code):Q.S.require(value,code)
def digest(value):return type(value) is str and HEX.fullmatch(value)

def results(spool):
    spool=W.private_directory(spool);found=[]
    for path in spool.iterdir():
        if not HEX.fullmatch(path.name):continue
        require(len(found)<W.MAX_RESULTS,'BRIDGE_RESULT_LIMIT');W.private_directory(path)
        raw=W.read_file(path/'receipt.json',65536);value=json.loads(raw)
        require(type(value) is dict and set(value)=={'schema_version','job_key','proposal','base_sha256','base_policy_sha256',
            'proposal_sha256','policy_sha256','deployment_authorized'} and value['schema_version']==1
            and value['deployment_authorized'] is False,'BRIDGE_RECEIPT_FIELDS')
        Q.checked(value['proposal'])
        require(Q.key(value['proposal'])==value['job_key'] and all(digest(value[k]) for k in
            ('job_key','base_sha256','base_policy_sha256','proposal_sha256','policy_sha256')),'BRIDGE_RECEIPT_BINDING')
        identity={k:value[k] for k in ('schema_version','job_key','proposal','base_sha256','base_policy_sha256')}
        require(sha(encode(identity))==path.name,'BRIDGE_RESULT_NAME')
        found.append((path,sha(raw),value))
    return found

def decisions(queue,spool,directory,now,*,owner=0):
    """Crash-safe: committed acknowledgements remain recognizable after restart."""
    directory=Path(directory)
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        require(info.st_uid==owner and stat.S_IMODE(info.st_mode)==0o755,'BRIDGE_DECISION_DIRECTORY')
        applied=0
        for path,receipt,value in results(spool):
            key=value['job_key'];name=key+'-'+receipt+'.json'
            try:child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            except FileNotFoundError:continue
            try:
                before=os.fstat(child)
                require(stat.S_ISREG(before.st_mode) and before.st_uid==owner and before.st_nlink==1
                    and stat.S_IMODE(before.st_mode)==0o444 and 0<before.st_size<=4096,'BRIDGE_DECISION_FILE')
                raw=os.read(child,4097);after=os.fstat(child)
                signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                require(len(raw)==before.st_size and signature(before)==signature(after),'BRIDGE_DECISION_CHANGED')
            finally:os.close(child)
            decision=json.loads(raw)
            require(type(decision) is dict and set(decision)=={'schema_version','key','receipt','action'}
                and decision['schema_version']==1 and decision['key']==key and decision['receipt']==receipt
                and decision['action'] in {'captured','reprepare'},'BRIDGE_DECISION_FIELDS')
            row=queue.db.execute('SELECT state,receipt FROM jobs WHERE key=?',(key,)).fetchone()
            require(row is not None,'BRIDGE_JOB_ABSENT')
            if decision['action']=='captured':
                queue.acknowledge(key,receipt,now)
            elif row['state']=='ready' and row['receipt']==receipt:
                queue.reprepare(key,receipt,now)
            else:
                # A previous invocation may already have committed reprepare.
                # Never apply an old decision to the replacement receipt.
                require(row['receipt']!=receipt,'BRIDGE_REPREPARE_CONFLICT')
            require(shutil.rmtree.avoids_symlink_attacks,'BRIDGE_SAFE_REMOVAL_REQUIRED')
            shutil.rmtree(path);W.sync_directory(spool);applied+=1
        return applied
    finally:os.close(fd)

def export(queue,spool,state):
    state=W.private_directory(state)
    indexed={receipt:(path,value) for path,receipt,value in results(spool)}
    rows=queue.ready();require(len(rows)<=W.MAX_RESULTS,'BRIDGE_READY_LIMIT')
    ready=[]
    for job in rows:
        require(job['receipt'] in indexed,'BRIDGE_RESULT_MISSING')
        path,value=indexed[job['receipt']]
        require(job['key']==value['job_key'] and json.loads(job['proposal'])==value['proposal'],'BRIDGE_JOB_CHANGED')
        ready.append({'job':job,'result':path.name,'base_sha256':value['base_sha256'],
            'base_policy_sha256':value['base_policy_sha256']})
    raw=encode({'schema_version':1,'ready':ready,'deployment_authorized':False})
    require(len(raw)<=65536,'BRIDGE_SNAPSHOT_LIMIT')
    fd=os.open(state/'ready.next',os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
    os.replace(state/'ready.next',state/'ready.json');W.sync_directory(state)
    return len(ready)
