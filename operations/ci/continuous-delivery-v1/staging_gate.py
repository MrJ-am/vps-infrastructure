"""Read-only acceptance gate over the protected staging lease and journal.

The staging adapter is the only writer. The caller holds the shared environment
lock through this check, durable acceptance acquisition, and the merge request.
Candidate preparation receipts do not satisfy this gate.
"""
import json,os,re
import admission_orchestrator as O
import acceptance_commit as K
import contract as C
import delivery_environment as E,staging_runtime as R
from source_snapshot import require

FIELDS={'schema_version','job','proposal_sha256','base_sha256','plan_sha256','system'}
STORE=re.compile('/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+\\Z')

def runtime_ready(record,lease):
    environment=E.read()
    require(environment['system']==lease['system'],'STAGING_LIVE_OR_BOOT_CHANGED')
    R.verify(record,environment)

def ready(state,job,*,observe=None,check_runtime=runtime_ready):
    O.W.private_directory(state)
    require(job['phase']=='validated' and job.get('promotion') is None,'STAGING_JOB_NOT_AVAILABLE')
    lease=json.loads(C.regular_file(state/'lease.json',owner=os.getuid(),mode=0o600,maximum=65536))
    expected=K.identity(job)
    require(type(lease) is dict and set(lease)==FIELDS
        and type(lease['schema_version']) is int
        and all(lease[k]==v for k,v in expected.items())
        and type(lease['plan_sha256']) is str and K.HEX.fullmatch(lease['plan_sha256'])
        and type(lease['system']) is str and STORE.fullmatch(lease['system']),
        'STAGING_LEASE_BINDING_REFUSED')
    records=O.W.private_directory(state/'records')
    journal=json.loads(C.regular_file(records/(lease['plan_sha256']+'.json'),owner=os.getuid(),mode=0o600,maximum=65536))
    require(type(journal) is dict and set(journal)==FIELDS|{'phase','runtime'}
        and all(journal[k]==v for k,v in lease.items()) and journal['phase']=='ready',
        'STAGING_NOT_READY')
    current,boot=(observe() if observe is not None else
        (os.path.realpath('/run/current-system'),os.path.realpath('/nix/var/nix/profiles/system')))
    require(current==boot==lease['system'],'STAGING_LIVE_OR_BOOT_CHANGED')
    check_runtime(journal['runtime'],lease)
    return lease
