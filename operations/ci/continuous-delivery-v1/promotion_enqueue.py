"""Publish one verified root promotion plan after staged acceptance and sync.

Caller holds the adoption lock. No activation commands or remote write identity.
Historical plans require matching completion, or a proven ViSe return.
"""
import os,time
import accepted_receipts as Accepted
import contract as C,admission_orchestrator as O
import acceptance_pipeline as A,staging_lease as L,promotion_reservation as R

def compose(stage,job,ledger):
    L.identity(stage);A.checked(ledger,job)
    number,review=Accepted.checked(stage,job,ledger)
    return {'schema_version':1,'job':stage['job'],'proposal_sha256':stage['proposal_sha256'],
        'old':stage['staged']['system'],'new':stage['promoted']['system'],'slot':stage['slot'],
        'bundle':stage['bundle'],'forge_pull':number,'review':review}

def completed(state,jobs,plan):
    marker=R.identity(plan);key=marker['plan_sha256']
    journal=L.read(state/(key+'.json'))
    returned=plan.get('profile')=='vise-v1' and journal=={
        'schema_version':1,'plan_sha256':key,'phase':'failed'}
    C.require(returned or journal=={'schema_version':1,'plan_sha256':key,'phase':'complete'},
        'ENQUEUE_PREVIOUS_PROMOTION_PENDING')
    job=O.read(O.W.private_directory(jobs/plan['job'])/'state.json')
    C.require(job['id']==plan['job'] and job['capture']['proposal_sha256']==plan['proposal_sha256']
        and job.get('promotion') is None,'ENQUEUE_PREVIOUS_RECEIPT_REFUSED')
    if returned:
        C.require(job['phase']=='validated' and job.get('delivery') is None
            and job.get('delivery_return')=={'plan_sha256':key,'generation':plan['old']},
            'ENQUEUE_FAILED_RETURN_UNPROVEN')
        return
    C.require(job['phase']=='deployed' and job.get('delivery')=={
        'plan_sha256':key,'proposal_sha256':plan['proposal_sha256'],'generation':plan['new'],
        'previous_generation':plan['old']},'ENQUEUE_PREVIOUS_RECEIPT_REFUSED')

def enqueue(state,roots,jobs,plan,*,authorize,ready,observe,clock=time.time):
    O.W.private_directory(state);O.W.private_directory(jobs)
    marker=R.identity(plan);key=marker['plan_sha256'];destination=state/'plan.json'
    previous=L.read(destination) if destination.exists() else None
    if previous is not None and previous!=plan:completed(state,jobs,previous)
    C.require(observe()==(plan['old'],plan['old']),'ENQUEUE_STAGED_GENERATION_CHANGED')
    ready();authorize(plan);ready()
    C.require(observe()==(plan['old'],plan['old']),'ENQUEUE_STAGED_GENERATION_CHANGED')
    if previous==plan:
        journal=state/(key+'.json')
        if journal.exists():
            value=L.read(journal)
            C.require(set(value)=={'schema_version','plan_sha256','phase'} and value['schema_version']==1
                and value['plan_sha256']==key,'ENQUEUE_JOURNAL_REFUSED')
            if value['phase']=='failed':
                job=O.read(O.W.private_directory(jobs/plan['job'])/'state.json')
                C.require(job['phase']=='validated' and job.get('promotion') is None
                    and job.get('delivery_return')=={'plan_sha256':key,'generation':plan['old']},
                    'ENQUEUE_FAILED_RETURN_UNPROVEN')
                retry=state/('retry-'+key+'.json');now=int(clock())
                attempts=0
                if retry.exists():
                    last=L.read(retry)
                    C.require(set(last)=={'attempts','next_attempt'} and all(type(v) is int and v>=0 for v in last.values()),
                        'ENQUEUE_RETRY_REFUSED')
                    if now<last['next_attempt']:return {'code':'PROMOTION_RETRY_WAIT','plan_sha256':key}
                    attempts=last['attempts']
                O.save(state/('last-failure-'+key+'.json'),value)
                O.save(retry,{'attempts':attempts+1,'next_attempt':now+300})
                O.save(journal,{'schema_version':1,'plan_sha256':key,'phase':'prepared'})
            else:C.require(value['phase'] in {'prepared','new-tested','returned','active','boot','commit-ready'},
                'ENQUEUE_PROMOTION_REQUIRES_RECOVERY')
        return {'code':'PROMOTION_PLAN_PRESENT','plan_sha256':key}
    roots.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(roots)
    for label in ('old','new'):
        link=roots/(key+'-'+label)
        if link.is_symlink():C.require(os.readlink(link)==plan[label],'ENQUEUE_GC_ROOT_COLLISION')
        else:
            C.require(not link.exists(),'ENQUEUE_GC_ROOT_COLLISION');os.symlink(plan[label],link)
    O.W.sync_directory(roots)
    O.save(destination,plan)
    return {'code':'PROMOTION_PLAN_ENQUEUED','plan_sha256':key}
