"""Recheck a ViSe preparation before acceptance, without live activation.

The caller holds the shared environment lock and supplies the installed recipe
and signature verifier. This data-only plan grants no merge/deployment authority.
The signed isolated validation substitutes for no production check: transition
still has to prove availability and real return after protected acceptance.
"""
import json,os
from pathlib import Path
import contract as C,admission_orchestrator as O,acceptance_commit as K
import delivery_constructor as D,generation_views as G,delivery_profiles as Profiles
import host_views as V,generation_layout as L

def document(work,name):
    return C.regular_file(work/name,owner=os.getuid(),mode=0o600,maximum=65536)

def create(work,job_root,job,environment,verify,*,recipe):
    O.W.private_directory(work);G.state_checked(environment)
    C.require(job['phase']=='validated' and job.get('promotion') is None,
        'VISE_PREPARATION_JOB_REFUSED')
    C.require(Profiles.selected(job['capture']['proposal'])=='vise','VISE_PREPARATION_PROFILE_REFUSED')
    identity=K.identity(job)
    binding=D.vise_binding(job_root,job,verify)
    binding_raw=document(work,'binding.json')
    C.require(binding_raw==O.encode(binding),'VISE_PREPARATION_BINDING_CHANGED')
    raw=document(work,'input-state.json');state=json.loads(raw)
    C.require(state==environment,'VISE_PREPARATION_BASE_CHANGED')
    inputs=json.loads(document(work,'inputs.json'))
    C.exact(inputs,{'schema_version','profile','state','candidate','recipe'})
    C.require(type(inputs['schema_version']) is int and inputs['schema_version']==1
        and inputs['profile']=='vise-v1' and inputs['state']==state
        and inputs['recipe']==str(recipe) and G.store(inputs['candidate']),
        'VISE_PREPARATION_INPUT_REFUSED')
    path=inputs['candidate'];candidate=json.loads(L.read(Path(path,'descriptor.json')))
    C.require(candidate['schema_version']==2 and candidate['profile']=='vise-v1'
        and candidate['deployment_authorized'] is False
        and candidate['proposal_sha256']==identity['proposal_sha256']
        and candidate['binding_sha256']==C.sha(binding_raw)
        and candidate['source']==binding['source'] and candidate['policy']==binding['report_policy']
        and candidate['verification_sha256']==binding['verification_sha256'],
        'VISE_PREPARATION_CANDIDATE_CHANGED')
    views={phase:json.loads(document(work,'view-'+phase+'.json')) for phase in ('current','candidate')}
    proof=V.verify(views,raw,path,candidate)
    layout=L.verify(state['system'],proof['system'],path,previous_adopted=state.get('vise',{}).get('adopted'))
    expected={**proof,'built':True,'layout':layout,
        'view_sha256':{phase:C.sha(O.encode(v)) for phase,v in views.items()}}
    C.require(json.loads(document(work,'prepared.json'))==expected,'VISE_PREPARATION_RECEIPT_CHANGED')
    ready_raw=document(work,'ready.json')
    C.require(json.loads(ready_raw)=={**expected,'job':identity['job'],
        'proposal_sha256':identity['proposal_sha256'],'environment_sha256':C.sha(O.encode(environment)),
        'ready_for_staging':True,'deployment_authorized':False},'VISE_PREPARATION_READY_CHANGED')
    return {**identity,'profile':'vise-v1','old':state['system'],'new':proof['system'],
        'environment':environment,'candidate':path,'bundle':candidate['bundle'],
        'adopted':candidate['adopted'],'previous_artifact':views['current']['artifact'],
        'preparation_sha256':C.sha(ready_raw),'deployment_authorized':False}
