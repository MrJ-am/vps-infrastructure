"""Select accepted ViSe work under the shared lock; never run candidate code.

Active transitions always resume first. A returned attempt is not retried by
this timer: another accepted proposal may proceed, including platform work.
"""
from pathlib import Path
import contract as C,admission_orchestrator as O,acceptance_commit as K
import acceptance_pipeline as A,delivery_profiles as Profiles
import promotion_enqueue as N,staging_lease as L
import enqueue as E

JOBS=Path('/var/lib/mrjam-intake-admission/jobs')
ACCEPTANCE=Path('/var/lib/mrjam-acceptance')
STAGING=Path('/var/lib/mrjam-staging')
ROOTS=Path('/nix/var/nix/gcroots/mrjam-delivery')

def tick(state,credential,*,jobs=JOBS,acceptance=ACCEPTANCE,staging=STAGING,roots=ROOTS):
    O.W.private_directory(state)
    previous=None
    destination=state/'plan.json'
    if destination.exists() or destination.is_symlink():
        previous=L.read(destination);key=N.R.identity(previous)['plan_sha256']
        journal=state/(key+'.json')
        if not journal.exists():return None
        record=L.read(journal)
        C.require(type(record) is dict and set(record)=={'schema_version','plan_sha256','phase'}
            and type(record['schema_version']) is int and record['schema_version']==1
            and record['plan_sha256']==key,'VISE_QUEUE_JOURNAL_REFUSED')
        if record['phase'] not in {'complete','failed'}:return None
        # Platform failures remain owned by the existing platform retry path.
        if record['phase']=='failed' and previous.get('profile')!='vise-v1':return None
        N.completed(state,jobs,previous)
    for directory in (jobs,acceptance,staging):O.W.private_directory(directory)
    lease=staging/'lease.json'
    if lease.exists() or lease.is_symlink():return {'code':'VISE_QUEUE_PLATFORM_PENDING'}
    owner_path=acceptance/'commit.json'
    if not owner_path.exists():return {'code':'VISE_QUEUE_IDLE'}
    owner=L.read(owner_path)
    C.require(type(owner) is dict and type(owner.get('job')) is str
        and K.HEX.fullmatch(owner['job']),'VISE_QUEUE_OWNER_REFUSED')
    directory=O.W.private_directory(jobs/owner['job']);job=O.read(directory/'state.json')
    C.require(K.identity(job)==owner,'VISE_QUEUE_OWNER_CHANGED')
    if job['phase']!='validated' or job.get('promotion') is not None:return {'code':'VISE_QUEUE_IDLE'}
    if Profiles.selected(job['capture']['proposal'])!='vise':return {'code':'VISE_QUEUE_PLATFORM_PENDING'}
    if previous is not None and previous['job']==job['id']:
        return {'code':'VISE_QUEUE_RETURNED','job':job['id']}
    ledger_path=acceptance/job['id']
    if not (ledger_path/'state.json').exists():return {'code':'VISE_QUEUE_ACCEPTANCE_PENDING'}
    O.W.private_directory(ledger_path);ledger=A.checked(L.read(ledger_path/'state.json'),job)
    if set(ledger['receipts'])!=set(A.STAGES) or ledger['inflight'] is not None:
        return {'code':'VISE_QUEUE_ACCEPTANCE_PENDING'}
    # Only the immutable accepted plan is considered; publish rechecks all
    # receipts, signed authority, live environment and generation layout.
    return E.publish(state,roots,jobs,acceptance,job['id'],credential())
