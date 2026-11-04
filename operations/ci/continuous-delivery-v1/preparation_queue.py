"""Durable, fair preparation queue; caller holds the shared environment lock."""
import json,re,time
from pathlib import Path
import admission_orchestrator as O
from source_snapshot import require

FIELDS={'schema_version','job','proposal_sha256','environment_sha256','phase','attempts','next_attempt','code'}

def tick(jobs,state,adapter,*,clock=time.time):
    O.W.private_directory(jobs);O.W.private_directory(state);entries=[];now=int(clock())
    for count,directory in enumerate(jobs.iterdir(),1):
        require(count<=O.MAX_JOBS and re.fullmatch('[0-9a-f]{64}',directory.name),'PREPARATION_JOB_LIMIT')
        O.W.private_directory(directory)
        if (directory/'state.json').exists():entries.append((directory,O.read(directory/'state.json')))
    if any(j['phase'] in O.ACTIVE for _,j in entries):return {'code':'PREPARATION_CI_BUSY'}
    environment=adapter.environment();environment_sha=O.sha(O.encode(environment))
    for directory,job in sorted(entries,key=lambda item:item[1]['id']):
        if job['phase']!='validated' or job.get('promotion') is not None or not adapter.supports(job):continue
        digest=job['capture']['proposal_sha256'];require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest),'PREPARATION_DIGEST_REFUSED')
        parent=state/job['id'];parent.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(parent)
        work=parent/environment_sha;work.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(work)
        journal=work/'progress.json'
        value={'schema_version':1,'job':job['id'],'proposal_sha256':digest,'environment_sha256':environment_sha,
            'phase':'pending','attempts':0,'next_attempt':now,'code':None}
        if journal.exists():
            existing=json.loads(O.W.read_file(journal,65536))
            require(type(existing) is dict and set(existing)==FIELDS
                and all(existing[k]==value[k] for k in ('schema_version','job','proposal_sha256','environment_sha256'))
                and existing['phase'] in {'pending','preparing','prepared','retry'}
                and all(type(existing[k]) is int and existing[k]>=0 for k in ('attempts','next_attempt')),
                'PREPARATION_JOURNAL_REFUSED')
            value=existing
        if value['phase']=='prepared' and (work/'ready.json').exists():
            receipt=json.loads(O.W.read_file(work/'ready.json',65536))
            require(receipt['job']==job['id'] and receipt['proposal_sha256']==digest
                and receipt['environment_sha256']==environment_sha and receipt['deployment_authorized'] is False,
                'PREPARATION_CACHED_BINDING_REFUSED')
            continue
        if value['next_attempt']>now:continue
        value['phase']='preparing';O.save(journal,value)
        try:
            receipt=adapter.prepare(directory,work,job,environment)
            require(receipt['job']==job['id'] and receipt['proposal_sha256']==digest
                and receipt['environment_sha256']==environment_sha and receipt['deployment_authorized'] is False,
                'PREPARATION_RESULT_BINDING_REFUSED')
            O.save(work/'ready.json',receipt)
            value.update(phase='prepared',code=None);O.save(journal,value)
            return {'code':'PREPARATION_COMPLETE','job':job['id'],'deployment_authorized':False}
        except Exception as error:
            code=str(error) if type(error).__name__=='Refused' else 'PREPARATION_RETRY'
            if not re.fullmatch('[A-Z_]{1,80}',code):code='PREPARATION_RETRY'
            value.update(phase='retry',code=code,attempts=value['attempts']+1,next_attempt=now+300);O.save(journal,value)
            return {'code':code,'job':job['id'],'deployment_authorized':False}
    return {'code':'PREPARATION_IDLE','deployment_authorized':False}
