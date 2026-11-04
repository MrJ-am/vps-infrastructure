"""Bind a protected preparation to a fixed off-traffic activation plan.

Called under the environment lock before acquiring the staging lease. Source
and artifact authority is checked again; preparation booleans alone authorize
nothing. The plan contains data only and cannot select an executable command.
"""
import json,os
from pathlib import Path
import contract as C,admission_orchestrator as O
import delivery_constructor as D,generation_views as G,acceptance_commit as K
import staging_layout as B

def document(work,name):
    return C.regular_file(work/name,owner=os.getuid(),mode=0o600,maximum=65536)

def create(work,job_root,job,environment,verify):
    O.W.private_directory(work);G.state_checked(environment)
    identity=K.identity(job)
    slot='green' if environment['active_slot']=='blue' else 'blue'
    binding=D.binding(job_root,job,slot,environment['slots'][slot]['runtime'],verify)
    binding_raw=document(work,'binding.json')
    C.require(binding_raw==O.encode(binding),'STAGING_BINDING_CHANGED')
    raw=document(work,'input-state.json');state=json.loads(raw)
    C.require(state==environment,'STAGING_PREPARATION_BASE_CHANGED')
    inputs=json.loads(document(work,'inputs.json'))
    C.exact(inputs,{'schema_version','state','candidate','recipe'})
    C.require(inputs['schema_version']==1 and inputs['state']==state and G.store(inputs['candidate']),
        'STAGING_PREPARATION_INPUT_REFUSED')
    candidate_path=inputs['candidate'];candidate=json.loads(Path(candidate_path,'descriptor.json').read_bytes())
    C.require(candidate['proposal_sha256']==identity['proposal_sha256']
        and candidate['binding_sha256']==C.sha(binding_raw)
        and candidate['source']==binding['source'] and candidate['policy']==binding['report_policy'],
        'STAGING_CANDIDATE_BINDING_REFUSED')
    C.require(G.store(candidate['bundle']),'STAGING_BUNDLE_PATH_REFUSED')
    bundle=json.loads(Path(candidate['bundle'],'descriptor.json').read_bytes())
    views={phase:json.loads(document(work,'view-'+phase+'.json')) for phase in ('current','stage','promotion')}
    proof=G.verify(views,state,raw,candidate_path,candidate,bundle)
    expected={**proof,'candidate':candidate_path,'input_state_sha256':C.sha(raw),
        'view_sha256':{phase:C.sha(O.encode(v)) for phase,v in views.items()},'built':True}
    C.require(json.loads(document(work,'prepared.json'))==expected,'STAGING_PREPARED_RECEIPT_CHANGED')
    ready_raw=document(work,'ready.json');ready=json.loads(ready_raw)
    C.require(ready=={**expected,'job':identity['job'],'proposal_sha256':identity['proposal_sha256'],
        'environment_sha256':C.sha(O.encode(environment)),'ready_for_staging':True,'deployment_authorized':False},
        'STAGING_READY_RECEIPT_CHANGED')
    # Nix unit.text can describe a drop-in or a masked unit rather than its
    # installed main file. Compare the entire built layout independently.
    B.verify(environment,proof['stagedState'],proof['promotedState'],slot)
    return {**identity,'slot':slot,'old':environment,'staged':proof['stagedState'],'promoted':proof['promotedState'],
        'candidate':candidate_path,'bundle':candidate['bundle'],'preparation_sha256':C.sha(ready_raw)}
