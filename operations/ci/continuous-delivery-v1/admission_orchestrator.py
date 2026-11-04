"""Durable orchestration of protected capture, admission, CI and signed output.

Installed adapters own all external operations. The journal fixes validity and
the run lower bound before side effects. A validated job still awaits protected
review/promotion; no CI status alone grants production authority.
"""
import fcntl,json,os,re,stat,time
from pathlib import Path
import intake_prepare as W
from proposal_prepare import encode,sha
from source_snapshot import require

PHASES={'pending','captured','constructed','admitted','dispatching','running','validated','failed','obsolete','deployed'}
ACTIVE={'admitted','dispatching','running'}
MAX_JOBS=64

def save(path,value):
    raw=encode(value);require(len(raw)<=65536,'ORCHESTRATOR_JOURNAL_LIMIT')
    temporary=path.with_suffix('.next')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
    os.replace(temporary,path);W.sync_directory(path.parent)

def read(path):
    value=json.loads(W.read_file(path,65536))
    require(type(value) is dict and value.get('schema_version')==1 and value.get('phase') in PHASES,'ORCHESTRATOR_JOURNAL_REFUSED')
    require(type(value.get('id')) is str and re.fullmatch('[0-9a-f]{64}',value['id'])
        and path.parent.name==value['id'],'ORCHESTRATOR_JOB_REFUSED')
    marker=value.get('promotion')
    if marker is not None:
        require(type(marker) is dict and set(marker)=={'schema_version','plan_sha256','proposal_sha256'}
            and type(marker['schema_version']) is int and marker['schema_version']==1
            and all(type(marker[k]) is str and re.fullmatch('[0-9a-f]{64}',marker[k])
                for k in ('plan_sha256','proposal_sha256'))
            and value['phase']=='validated' and marker['proposal_sha256']==value.get('capture',{}).get('proposal_sha256'),
            'ORCHESTRATOR_PROMOTION_MARKER_REFUSED')
    return value

def identity(ready):return sha(encode({k:ready['job'][k] for k in ('key','receipt')}))

def tick(root,ready,adapter,*,clock=time.time):
    """At most one side-effecting transition per call, under a controller lock.

    The production caller additionally holds the shared deployment/adoption
    transaction lock. `ready` is an untrusted bounded bridge snapshot.
    """
    root=W.private_directory(root)
    fd=os.open(root/'controller.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and stat.S_IMODE(info.st_mode)==0o600,'ORCHESTRATOR_LOCK_REFUSED')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'code':'ORCHESTRATOR_BUSY'}
        jobs=root/'jobs'
        try:jobs.mkdir(mode=0o700)
        except FileExistsError:pass
        W.private_directory(jobs)
        entries=[];count=0
        for path in jobs.iterdir():
            count+=1;require(count<=MAX_JOBS,'ORCHESTRATOR_CAPACITY')
            require(re.fullmatch('[0-9a-f]{64}',path.name),'ORCHESTRATOR_UNKNOWN_ENTRY')
            W.private_directory(path);require(len(entries)<MAX_JOBS,'ORCHESTRATOR_CAPACITY')
            # A crash between mkdir and the initial journal write leaves only
            # an empty controlled directory; it can be reinitialized below.
            if (path/'state.json').exists():entries.append((path,read(path/'state.json')))
            else:
                partial=path/'state.next'
                if partial.exists():
                    require(set(p.name for p in path.iterdir())=={'state.next'},'ORCHESTRATOR_PARTIAL_JOURNAL')
                    # Only an initial pending journal can exist before the
                    # first durable state.json. No external action has run.
                    W.read_file(partial,65536);partial.unlink();W.sync_directory(path)
                require(not list(path.iterdir()),'ORCHESTRATOR_PARTIAL_JOURNAL')
        require(type(ready) is list and len(ready)<=16,'ORCHESTRATOR_READY_LIMIT')
        known={value['id'] for _,value in entries};now=int(clock())
        for item in ready:
            adapter.check_ready(item)
            identifier=identity(item)
            if identifier in known:continue
            require(len(entries)<MAX_JOBS,'ORCHESTRATOR_CAPACITY')
            path=jobs/identifier
            try:path.mkdir(mode=0o700)
            except FileExistsError:require(not list(path.iterdir()),'ORCHESTRATOR_PARTIAL_JOURNAL')
            value={'schema_version':1,'id':identifier,'ready':item,'phase':'pending','created':now,
                'updated':now,'next_attempt':now,'attempts':0,'code':None}
            save(path/'state.json',value);entries.append((path,value));known.add(identifier)
        active=[(path,value) for path,value in entries if value['phase'] in ACTIVE]
        require(len(active)<=1,'ORCHESTRATOR_MULTIPLE_ACTIVE_CI')
        candidates=active or sorted(((path,value) for path,value in entries
            if value['phase'] not in {'failed','obsolete','deployed'}),key=lambda pair:(pair[1]['next_attempt'],pair[1]['created'],pair[1]['id']))
        promotion_pending=False
        for path,value in candidates:
            # A root-owned, durable intent is written before changing the
            # adopted generation. Recovery owns this job until it atomically
            # records success or restores the previous generation. In
            # particular a reboot must never turn this job into "obsolete".
            if value.get('promotion') is not None:
                promotion_pending=True;continue
            if value['next_attempt']>now:continue
            try:
                if value['phase']=='validated':
                    # A profile's metadata failure must be recorded on this
                    # job, not escape the per-job retry boundary.
                    if adapter.current(value) and value.get('feedback') is not None:continue
                advance(path,value,adapter,now)
                value.update(updated=now,next_attempt=max(now,value['next_attempt']),code=None)
                save(path/'state.json',value)
                return {'code':'ORCHESTRATOR_ADVANCED','job':value['id'],'phase':value['phase'],'deployment_authorized':False}
            except Exception as error:
                code=str(error) if type(error).__name__=='Refused' else 'ORCHESTRATOR_RETRY'
                if not re.fullmatch('[A-Z_]{1,80}',code):code='ORCHESTRATOR_RETRY'
                value.update(updated=now,next_attempt=now+300,attempts=value['attempts']+1,code=code)
                save(path/'state.json',value)
                return {'code':code,'job':value['id'],'phase':value['phase'],'deployment_authorized':False}
        return {'code':'ORCHESTRATOR_DELIVERY_PENDING' if promotion_pending else 'ORCHESTRATOR_IDLE','deployment_authorized':False}
    finally:os.close(fd)

def advance(path,value,adapter,now):
    phase=value['phase']
    # Running CI is reconciled to its terminal state before another job can
    # replace its staged inputs, even if the adopted base changed meanwhile.
    if phase not in {'dispatching','running'} and not adapter.current(value):
        adapter.decision(value,'reprepare');value['phase']='obsolete';return
    if phase=='pending':
        value['capture']=adapter.capture(path,value)
        value['validity']={'not_before':now,'expires_at':now+604800}
        value['phase']='captured'
    elif phase=='captured':
        value['bundle']=adapter.construct(path,value)
        value['phase']='constructed'
    elif phase=='constructed':
        adapter.observe(value);adapter.admit(path,value)
        value['phase']='admitted'
    elif phase=='admitted':
        # Persist before POST, so a lost response is reconciled by exact input
        # and this fixed run boundary on the next tick.
        adapter.observe(value)
        value['after_id']=adapter.run_boundary(value)
        value['phase']='dispatching'
    elif phase=='dispatching':
        value['run']=adapter.dispatch(value);value['phase']='running'
    elif phase=='running':
        result=adapter.poll(value);value['run']=result
        if not result['terminal']:value['next_attempt']=now+30;return
        if result['status']!='success':
            adapter.decision(value,'captured');value['phase']='failed';return
        if not adapter.current(value):
            adapter.decision(value,'reprepare');value['phase']='obsolete';return
        value['artifacts']=adapter.capture_artifacts(path,value)
        value['phase']='validated'
    elif phase=='validated':
        value['feedback']=adapter.feedback(path,value)
    else:require(False,'ORCHESTRATOR_PHASE_REFUSED')
