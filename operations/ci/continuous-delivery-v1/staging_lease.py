"""Durable single-owner staging reservation; caller holds the adoption lock."""
import json,os
import contract as C,admission_orchestrator as O
import acceptance_commit as K,generation_views as G,staging_transaction as T

def read(path):return json.loads(C.regular_file(path,owner=os.getuid(),mode=0o600,maximum=65536))

def identity(plan):
    C.exact(plan,{'schema_version','job','proposal_sha256','base_sha256','slot','old','staged','promoted',
        'candidate','bundle','preparation_sha256'})
    C.require(type(plan['schema_version']) is int and plan['schema_version']==1
        and all(G.digest(plan[k]) for k in ('job','proposal_sha256','base_sha256','preparation_sha256'))
        and all(G.store(plan[k]) for k in ('candidate','bundle')),'STAGING_PLAN_IDENTITY_REFUSED')
    for field in ('old','staged','promoted'):G.state_checked(plan[field])
    C.require(plan['slot'] in G.SLOTS and plan['slot']!=plan['old']['active_slot']
        and plan['staged']['active_slot']==plan['old']['active_slot'],'STAGING_PLAN_SLOT_REFUSED')
    return {k:plan[k] for k in ('schema_version','job','proposal_sha256','base_sha256')}|{
        'plan_sha256':C.sha(O.encode(plan)),'system':plan['staged']['system']}

def directories(state):
    O.W.private_directory(state)
    for name in ('plans','records'):
        (state/name).mkdir(mode=0o700,exist_ok=True);O.W.private_directory(state/name)

def pending_commit(acceptance,jobs):
    O.W.private_directory(acceptance);O.W.private_directory(jobs)
    if not (acceptance/'commit.json').exists():return None
    owner=read(acceptance/'commit.json')
    C.require(type(owner) is dict and set(owner)=={'schema_version','job','proposal_sha256','base_sha256'}
        and type(owner['schema_version']) is int and owner['schema_version']==1
        and all(G.digest(owner[k]) for k in ('job','proposal_sha256','base_sha256')),'STAGING_COMMIT_RECORD_REFUSED')
    directory=O.W.private_directory(jobs/owner['job']);job=O.read(directory/'state.json')
    C.require(K.identity(job)==owner,'STAGING_COMMIT_OWNER_CHANGED')
    delivery=job.get('delivery',{})
    if K.returned(job):return None
    if job['phase']=='deployed' and delivery.get('proposal_sha256')==owner['proposal_sha256'] and G.digest(delivery.get('plan_sha256')):
        return None
    return owner

def acquire(state,plan,acceptance,jobs,observe):
    directories(state);expected=identity(plan);key=expected['plan_sha256']
    if (state/'lease.json').exists():
        C.require(read(state/'lease.json')==expected,'STAGING_OTHER_DELIVERY_PENDING')
        C.require(read(state/'plans'/(key+'.json'))==plan,'STAGING_PLAN_CHANGED')
        return expected
    C.require(pending_commit(acceptance,jobs) is None,'STAGING_ACCEPTED_DELIVERY_PENDING')
    C.require(observe()==(plan['old']['system'],plan['old']['system']),'STAGING_INITIAL_BASE_CHANGED')
    plan_file=state/'plans'/(key+'.json');journal=state/'records'/(key+'.json')
    if plan_file.exists():C.require(read(plan_file)==plan,'STAGING_PLAN_CHANGED')
    else:O.save(plan_file,plan)
    if journal.exists():
        previous=read(journal)
        C.require(set(previous)==set(expected)|{'phase','runtime'}
            and all(previous[k]==v for k,v in expected.items()) and previous['phase'] in {'prepared','failed'},
            'STAGING_RELEASED_RECORD_REFUSED')
    # Publish the bound journal before making the plan available to workers.
    O.save(journal,{**expected,'phase':'prepared','runtime':None})
    O.save(state/'lease.json',expected)
    return expected

def checkpoint(state,plan,phase,runtime=None):
    expected=identity(plan);C.require(read(state/'lease.json')==expected,'STAGING_LEASE_CHANGED')
    C.require(phase in T.PHASES and (phase!='ready' or type(runtime) is dict),'STAGING_CHECKPOINT_REFUSED')
    O.save(state/'records'/(expected['plan_sha256']+'.json'),{**expected,'phase':phase,'runtime':runtime})

def release(state,plan,acceptance,jobs,observe):
    expected=identity(plan)
    C.require(observe()==(plan['old']['system'],plan['old']['system']),'STAGING_RETURN_NOT_PROVEN')
    owner=pending_commit(acceptance,jobs)
    C.require(owner is None or owner['job']!=plan['job'],'STAGING_AMBIGUOUS_ACCEPTANCE_RETAINED')
    journal=read(state/'records'/(expected['plan_sha256']+'.json'))
    C.require(journal=={**expected,'phase':'failed','runtime':None},'STAGING_FAILED_RECEIPT_REQUIRED')
    lease=state/'lease.json'
    if lease.exists():
        C.require(read(lease)==expected,'STAGING_LEASE_CHANGED')
        lease.unlink();O.W.sync_directory(state)

def complete(state,plan,job,promotion,observe):
    """Retire a stage only after the matching promotion durably completed."""
    expected=identity(plan)
    C.require(K.identity(job)=={k:plan[k] for k in ('schema_version','job','proposal_sha256','base_sha256')}
        and job['phase']=='deployed' and job.get('promotion') is None,'STAGING_DELIVERY_NOT_COMPLETE')
    O.W.private_directory(promotion)
    promoted=read(promotion/'plan.json');key=C.sha(O.encode(promoted))
    C.require(promoted.get('job')==plan['job'] and promoted.get('proposal_sha256')==plan['proposal_sha256']
        and promoted.get('old')==plan['staged']['system'] and promoted.get('new')==plan['promoted']['system']
        and promoted.get('slot')==plan['slot'] and promoted.get('bundle')==plan['bundle'],
        'STAGING_PROMOTION_PLAN_CHANGED')
    C.require(job.get('delivery')=={'plan_sha256':key,'proposal_sha256':plan['proposal_sha256'],
        'generation':plan['promoted']['system'],'previous_generation':plan['staged']['system']},
        'STAGING_DELIVERY_RECEIPT_CHANGED')
    C.require(read(promotion/(key+'.json'))=={'schema_version':1,'plan_sha256':key,'phase':'complete'},
        'STAGING_PROMOTION_NOT_COMPLETE')
    C.require(observe()==(plan['promoted']['system'],)*2,'STAGING_PROMOTED_GENERATION_CHANGED')
    journal=state/'records'/(expected['plan_sha256']+'.json');record=read(journal)
    C.require(set(record)==set(expected)|{'phase','runtime'} and all(record[k]==v for k,v in expected.items())
        and record['phase'] in {'ready','complete'},'STAGING_COMPLETION_RECORD_REFUSED')
    lease=state/'lease.json'
    if lease.exists():C.require(read(lease)==expected,'STAGING_LEASE_CHANGED')
    # A lost acknowledgement resumes from complete, not from an obsolete ready.
    O.save(journal,{**expected,'phase':'complete','runtime':None})
    if lease.exists():lease.unlink();O.W.sync_directory(state)
