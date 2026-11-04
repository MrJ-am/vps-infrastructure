"""Compose a ViSe transition only from its reserved plan and full acceptance.

This validates protected receipts, not current signature or remote state. The
caller must reauthorize both before enqueue and before each forward transition.
"""
import contract as C,admission_orchestrator as O,acceptance_commit as K
import accepted_receipts as A,delivery_profiles as Profiles,generation_views as G
import promotion_reservation as R
import staging_lease as L

FIELDS={'schema_version','job','proposal_sha256','base_sha256','profile','old','new',
    'environment','candidate','bundle','adopted','previous_artifact','preparation_sha256','deployment_authorized'}

def load(acceptance,jobs,job_id):
    C.require(G.digest(job_id),'VISE_ACCEPTED_JOB_PATH_REFUSED')
    O.W.private_directory(acceptance);O.W.private_directory(jobs)
    directory=O.W.private_directory(jobs/job_id)
    job=O.read(directory/'state.json')
    C.require(job['id']==job_id,'VISE_ACCEPTED_JOB_CHANGED')
    plans=O.W.private_directory(acceptance/'vise-plans')
    ledger=O.W.private_directory(acceptance/job_id)
    return compose(L.read(plans/(job_id+'.json')),L.read(acceptance/'commit.json'),job,
        L.read(ledger/'state.json'))

def compose(prepared,owner,job,ledger):
    C.exact(prepared,FIELDS)
    C.require(Profiles.selected(job['capture']['proposal'])=='vise'
        and prepared['profile']=='vise-v1' and prepared['deployment_authorized'] is False,
        'VISE_ACCEPTED_PROFILE_REFUSED')
    identity=K.identity(job)
    C.require(owner==identity and all(prepared[k]==v for k,v in identity.items()),'VISE_ACCEPTED_OWNER_CHANGED')
    R.identity(prepared);G.state_checked(prepared['environment'])
    C.require(prepared['environment']['system']==prepared['old']
        and all(G.store(prepared[k]) for k in ('candidate','bundle','adopted','previous_artifact'))
        and G.digest(prepared['preparation_sha256']),'VISE_ACCEPTED_PREPARATION_REFUSED')
    number,review=A.checked(prepared,job,ledger)
    return {'schema_version':1,'profile':'vise-v1','job':prepared['job'],
        'proposal_sha256':prepared['proposal_sha256'],'old':prepared['old'],'new':prepared['new'],
        'candidate':prepared['candidate'],'bundle':prepared['bundle'],'adopted':prepared['adopted'],
        'previous_artifact':prepared['previous_artifact'],'environment':prepared['environment'],
        'accepted_plan_sha256':O.sha(O.encode(prepared)),
        'acceptance_sha256':O.sha(O.encode(ledger)),'forge_pull':number,'review':review}
