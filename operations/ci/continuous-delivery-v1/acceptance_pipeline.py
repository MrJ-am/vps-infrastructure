"""Durable sequencing for independently credentialed acceptance services.

Caller holds the shared adoption lock. Each service can execute only its own
fixed stage; adapters independently recheck signed authority and remote state.
An inflight stage is recorded before its side effect and retried by that same
identity after a lost response. The ledger never grants deployment authority.
"""
import json,re,time
from pathlib import Path
import admission_orchestrator as O
from source_snapshot import require

STAGES=('mirror','review','merge','sync')

def checked(value,job):
    require(type(value) is dict and set(value)=={'schema_version','job','proposal_sha256','receipts','inflight','next_attempt','attempts','code'},
        'ACCEPTANCE_LEDGER_SHAPE_REFUSED')
    require(type(value['schema_version']) is int and value['schema_version']==1
        and value['job']==job['id'] and value['proposal_sha256']==job['capture']['proposal_sha256'],
        'ACCEPTANCE_LEDGER_IDENTITY_REFUSED')
    receipts=value['receipts'];require(type(receipts) is dict,'ACCEPTANCE_RECEIPTS_REFUSED')
    require(set(receipts)==set(STAGES[:len(receipts)]) and all(type(r) is dict for r in receipts.values()),
        'ACCEPTANCE_RECEIPTS_ORDER_REFUSED')
    expected=STAGES[len(receipts)] if len(receipts)<len(STAGES) else None
    require(value['inflight'] is None or value['inflight']==expected,'ACCEPTANCE_INFLIGHT_REFUSED')
    require(all(type(value[k]) is int and value[k]>=0 for k in ['next_attempt','attempts'])
        and (value['code'] is None or type(value['code']) is str and re.fullmatch('[A-Z_]{1,80}',value['code'])),
        'ACCEPTANCE_RETRY_REFUSED')
    return value

def tick(stage,jobs,state,adapter,*,clock=time.time):
    require(stage in STAGES,'ACCEPTANCE_STAGE_REFUSED')
    O.W.private_directory(state);O.W.private_directory(jobs);now=int(clock());entries=[]
    for count,directory in enumerate(jobs.iterdir(),1):
        require(count<=O.MAX_JOBS and re.fullmatch('[0-9a-f]{64}',directory.name),'ACCEPTANCE_JOB_LIMIT')
        O.W.private_directory(directory)
        if not (directory/'state.json').exists():continue
        job=O.read(directory/'state.json');entries.append((directory,job))
    for directory,job in sorted(entries,key=lambda pair:pair[1]['id']):
        if job['phase']!='validated' or job.get('promotion') is not None:continue
        require(type(job.get('capture',{}).get('proposal_sha256')) is str
            and re.fullmatch('[0-9a-f]{64}',job['capture']['proposal_sha256']),'ACCEPTANCE_JOB_DIGEST_REFUSED')
        destination=state/job['id']
        if destination.exists():O.W.private_directory(destination)
        journal=destination/'state.json'
        if journal.exists():value=checked(json.loads(O.W.read_file(journal,65536)),job)
        else:
            # Later identities cannot initialize or advance an unreceived job.
            if stage!='mirror':continue
            destination.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(destination)
            value={'schema_version':1,'job':job['id'],'proposal_sha256':job['capture']['proposal_sha256'],
                'receipts':{},'inflight':None,'next_attempt':now,'attempts':0,'code':None}
        if stage in value['receipts'] or len(value['receipts'])!=STAGES.index(stage) or value['next_attempt']>now:continue
        value['inflight']=stage;O.save(journal,value)
        try:
            receipt=adapter.execute(stage,directory,job,value['receipts'])
            require(type(receipt) is dict and receipt.get('repository')==job['capture']['proposal']['repository']
                and receipt.get('head')==job['capture']['proposal']['head'],'ACCEPTANCE_RESULT_BINDING_REFUSED')
            value['receipts'][stage]=receipt;value.update(inflight=None,next_attempt=now,code=None)
            checked(value,job);O.save(journal,value)
            return {'code':'ACCEPTANCE_STAGE_COMPLETE','stage':stage,'job':job['id'],'deployment_authorized':False}
        except Exception as error:
            code=str(error) if type(error).__name__=='Refused' else 'ACCEPTANCE_RETRY'
            if not re.fullmatch('[A-Z_]{1,80}',code):code='ACCEPTANCE_RETRY'
            value.update(next_attempt=now+300,attempts=value['attempts']+1,code=code)
            # Keep inflight and no receipt. Another identity cannot advance.
            O.save(journal,value)
            return {'code':code,'stage':stage,'job':job['id'],'deployment_authorized':False}
    return {'code':'ACCEPTANCE_IDLE','stage':stage,'deployment_authorized':False}
