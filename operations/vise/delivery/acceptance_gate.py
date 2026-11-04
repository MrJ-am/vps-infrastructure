"""Persist a reverified ViSe plan immediately before protected acceptance.

Caller holds the environment lock through this gate, acceptance_commit.acquire
and the merge request. No candidate process is started against production here.
An accepted plan cannot change, including after an ambiguous merge response.
"""
from pathlib import Path
import contract as C,admission_orchestrator as O,acceptance_commit as K
import staging_lease as L,delivery_environment as E
import preparation_plan as P

def ready(state,jobs,prepared,staging,job,verify,*,recipe,observe=E.read):
    for directory in (state,jobs,prepared,staging):O.W.private_directory(directory)
    lease=staging/'lease.json'
    C.require(not lease.exists() and not lease.is_symlink(),'VISE_OTHER_STAGE_PENDING')
    identity=K.identity(job);owner=L.pending_commit(state,jobs)
    C.require(owner is None or owner==identity,'VISE_OTHER_ACCEPTANCE_PENDING')
    environment=observe();key=O.sha(O.encode(environment))
    parent=O.W.private_directory(prepared/job['id'])
    work=O.W.private_directory(parent/key)
    job_root=O.W.private_directory(jobs/job['id'])
    plan=P.create(work,job_root,job,environment,verify,recipe=recipe)
    C.require(observe()==environment,'VISE_ACCEPTANCE_ENVIRONMENT_CHANGED')
    plans=state/'vise-plans';plans.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(plans)
    path=plans/(job['id']+'.json')
    if owner is not None:
        C.require(path.exists() and L.read(path)==plan,'VISE_ACCEPTED_PLAN_CHANGED')
    else:
        # A pre-merge retry may prepare against a newer base. Once commit.json
        # is acquired, the exact plan is retained until delivery completes.
        O.save(path,plan)
    return plan
