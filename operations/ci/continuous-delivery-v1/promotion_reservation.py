"""Durable root job reservation; independent authorization belongs to caller.

Caller holds the environment lock, has durably stored its immutable plan and
checks signed authority before any activation. No plan or journal supplied by
a candidate can invoke this installed component or write the root job store.
"""
import os,re
import admission_orchestrator as O
from source_snapshot import require

HEX=re.compile('[0-9a-f]{64}\\Z')
GENERATION=re.compile('/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-nixos-system-[A-Za-z0-9+._-]+\\Z')

def identity(plan):
    require(type(plan) is dict and type(plan.get('schema_version')) is int and plan['schema_version']==1
        and all(type(plan.get(k)) is str and HEX.fullmatch(plan[k]) for k in ['job','proposal_sha256'])
        and all(type(plan.get(k)) is str and GENERATION.fullmatch(plan[k]) for k in ['old','new'])
        and plan['old']!=plan['new'],'PROMOTION_PLAN_IDENTITY_REFUSED')
    return {'schema_version':1,'plan_sha256':O.sha(O.encode(plan)),'proposal_sha256':plan['proposal_sha256']}

def selected(path,plan):
    marker=identity(plan);value=O.read(path)
    require(value['id']==plan['job'] and value.get('capture',{}).get('proposal_sha256')==plan['proposal_sha256'],
        'PROMOTION_JOB_IDENTITY_REFUSED')
    return marker,value

def reserve(path,plan):
    marker,value=selected(path,plan)
    if value['phase']=='deployed':
        require(value.get('delivery',{}).get('plan_sha256')==marker['plan_sha256'],'PROMOTION_OTHER_DELIVERY_REFUSED')
        return
    require(value['phase']=='validated' and value.get('promotion') in (None,marker),'PROMOTION_RESERVATION_CONFLICT')
    if value.get('promotion') is None:value['promotion']=marker;O.save(path,value)

def actual():return (os.path.realpath('/run/current-system'),os.path.realpath('/nix/var/nix/profiles/system'))

def commit(path,plan,*,observe=actual):
    marker,value=selected(path,plan)
    require(observe()==(plan['new'],plan['new']),'PROMOTION_GENERATION_NOT_COMMITTED')
    if value['phase']=='deployed':
        require(value.get('delivery',{}).get('plan_sha256')==marker['plan_sha256'],'PROMOTION_OTHER_DELIVERY_REFUSED');return
    require(value['phase']=='validated' and value.get('promotion')==marker,'PROMOTION_RESERVATION_MISSING')
    value['phase']='deployed';value.pop('promotion');value['code']=None
    value['delivery']={'plan_sha256':marker['plan_sha256'],'proposal_sha256':plan['proposal_sha256'],
        'generation':plan['new'],'previous_generation':plan['old']}
    O.save(path,value)

def abort(path,plan,*,observe=actual):
    marker,value=selected(path,plan)
    require(observe()==(plan['old'],plan['old']),'PROMOTION_RETURN_NOT_CONFIRMED')
    require(value['phase']=='validated' and value.get('promotion')==marker,'PROMOTION_ABORT_CONFLICT')
    value.pop('promotion');value['delivery_return']={'plan_sha256':marker['plan_sha256'],'generation':plan['old']}
    O.save(path,value)
