"""Serialize irreversible acceptance until its deployment receipt is durable.

Caller holds the environment lock. Acquire immediately before the merge POST,
after all read-only checks. Never expire an ambiguous write on a timer: a lost
response may already have closed the proposal. Preflight failures acquire nothing.
This fence is coordination, not signature or deployment authority.
"""
import json,re
from pathlib import Path
import admission_orchestrator as O
from source_snapshot import require

HEX=re.compile('[0-9a-f]{64}\\Z')
PROMOTION=Path('/var/lib/mrjam-promotion')

def returned(job):
    """A root journal plus matching return receipt can retire failed ViSe.

    A bare failed job, merge receipt, or return receipt is insufficient. The
    journal becomes failed only after runtime/boot verification and job abort.
    Caller holds the shared environment lock while consuming this evidence.
    """
    receipt=job.get('delivery_return')
    if job['phase']!='validated' or job.get('promotion') is not None or job.get('delivery') is not None:
        return False
    if type(receipt) is not dict or set(receipt)!={'plan_sha256','generation'}:return False
    key=receipt['plan_sha256']
    if type(key) is not str or not HEX.fullmatch(key):return False
    O.W.private_directory(PROMOTION)
    plan=json.loads(O.W.read_file(PROMOTION/'plan.json',65536))
    if (O.sha(O.encode(plan))!=key or plan.get('profile')!='vise-v1'
            or plan.get('job')!=job['id'] or plan.get('proposal_sha256')!=job['capture']['proposal_sha256']
            or plan.get('old')!=receipt['generation']):return False
    journal=json.loads(O.W.read_file(PROMOTION/(key+'.json'),65536))
    return journal=={'schema_version':1,'plan_sha256':key,'phase':'failed'}

def identity(job):
    value={'schema_version':1,'job':job['id'],
        'proposal_sha256':job['capture']['proposal_sha256'],
        'base_sha256':job['ready']['base_sha256']}
    require(all(type(value[k]) is str and HEX.fullmatch(value[k])
        for k in ('job','proposal_sha256','base_sha256')),'ACCEPTANCE_COMMIT_IDENTITY_REFUSED')
    return value

def acquire(state,jobs,job):
    O.W.private_directory(state);O.W.private_directory(jobs)
    expected=identity(job);path=state/'commit.json'
    if path.exists():
        owner=json.loads(O.W.read_file(path,65536))
        require(type(owner) is dict and set(owner)==set(expected)
            and type(owner['schema_version']) is int and owner['schema_version']==1
            and all(type(owner[k]) is str and HEX.fullmatch(owner[k])
                for k in ('job','proposal_sha256','base_sha256')),'ACCEPTANCE_COMMIT_RECORD_REFUSED')
        if owner==expected:return
        directory=jobs/owner['job'];O.W.private_directory(directory)
        previous=O.read(directory/'state.json')
        require(identity(previous)==owner,'ACCEPTANCE_COMMIT_OWNER_CHANGED')
        delivery=previous.get('delivery',{})
        require(returned(previous) or (previous['phase']=='deployed'
            and delivery.get('proposal_sha256')==owner['proposal_sha256']
            and type(delivery.get('plan_sha256')) is str
            and HEX.fullmatch(delivery['plan_sha256'])),'ACCEPTANCE_PREVIOUS_DELIVERY_PENDING')
    # Atomic durable replace; there is no unlocked gap between owners.
    O.save(path,expected)
