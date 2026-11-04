"""One persistent off-traffic stage at a time; caller holds adoption lock."""
import re,time
import admission_orchestrator as O
import staging_lease as L
from source_snapshot import require

def tick(state,jobs,prepared,adapter,*,clock=time.time):
    O.W.private_directory(state);O.W.private_directory(jobs);O.W.private_directory(prepared)
    now=int(clock())
    if (state/'lease.json').exists():
        lease=L.read(state/'lease.json')
        require(type(lease) is dict and L.G.digest(lease.get('plan_sha256')),'STAGING_LEASE_REFUSED')
        plan=L.read(O.W.private_directory(state/'plans')/(lease['plan_sha256']+'.json'))
        require(L.identity(plan)==lease,'STAGING_PLAN_BINDING_REFUSED')
        directory=O.W.private_directory(jobs/plan['job']);job=O.read(directory/'state.json')
        require(L.K.identity(job)=={k:plan[k] for k in ('schema_version','job','proposal_sha256','base_sha256')},
            'STAGING_JOB_CHANGED')
        if job['phase']=='deployed':
            adapter.complete(plan,job)
            return {'code':'STAGING_DELIVERY_COMPLETE','job':job['id']}
        if job.get('promotion') is not None:
            return {'code':'STAGING_PROMOTION_PENDING','job':job['id']}
        result=adapter.stage(plan)
        if result['code']=='STAGING_FAILED':
            retry=state/'retry';retry.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(retry)
            O.save(retry/(job['id']+'.json'),{'schema_version':1,'job':job['id'],'next_attempt':now+300})
        return result
    entries=[]
    for count,directory in enumerate(jobs.iterdir(),1):
        require(count<=O.MAX_JOBS and re.fullmatch('[0-9a-f]{64}',directory.name),'STAGING_JOB_LIMIT')
        O.W.private_directory(directory)
        if (directory/'state.json').exists():entries.append((directory,O.read(directory/'state.json')))
    if any(job['phase'] in O.ACTIVE for _,job in entries):return {'code':'STAGING_CI_BUSY'}
    environment=adapter.environment();key=O.sha(O.encode(environment))
    for directory,job in sorted(entries,key=lambda item:item[1]['id']):
        if job['phase']!='validated' or job.get('promotion') is not None or not adapter.supports(job):continue
        retry=state/'retry'/(job['id']+'.json')
        if retry.exists():
            O.W.private_directory(retry.parent);value=L.read(retry)
            require(set(value)=={'schema_version','job','next_attempt'} and value['schema_version']==1
                and value['job']==job['id'] and type(value['next_attempt']) is int,'STAGING_RETRY_REFUSED')
            if value['next_attempt']>now:continue
        work=prepared/job['id']/key
        if not (work/'ready.json').exists():continue
        O.W.private_directory(work.parent);O.W.private_directory(work)
        try:plan=adapter.prepare(work,directory,job,environment)
        except Exception as error:
            retry.parent.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(retry.parent)
            O.save(retry,{'schema_version':1,'job':job['id'],'next_attempt':now+300})
            code=str(error) if type(error).__name__=='Refused' else 'STAGING_PREPARATION_RETRY'
            if not re.fullmatch('[A-Z_]{1,80}',code):code='STAGING_PREPARATION_RETRY'
            return {'code':code,'job':job['id']}
        adapter.acquire(plan)
        # Persisted reservation is the sole entrypoint for the next timer tick.
        return {'code':'STAGING_RESERVED','job':job['id']}
    return {'code':'STAGING_IDLE'}
