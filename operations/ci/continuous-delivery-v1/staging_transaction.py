"""Restartable off-traffic qualification before irreversible source acceptance.

The adapter holds the environment lock and a durable exclusive staging lease.
It validates a fixed plan and retains the public process/routing identities in
that plan. All operations are idempotent; checkpoints record observations, not
intent. A ready stage is immutable: a later caller might already have merged.
"""
from source_snapshot import require

PHASES={'prepared','tested','returned','active','boot','ready','failed','recovery-required'}

def replace(adapter,target):
    adapter.no_clients()
    adapter.stop_slot()
    adapter.switch(target)
    adapter.start_slot()
    adapter.verify(target,boot=False)

def restore(adapter):
    # Recovery never needs a still-valid candidate signature. The fixed old
    # generation and retained public route are validated by the adapter.
    replace(adapter,'old')
    adapter.boot('old')
    adapter.verify('old',boot=True)
    adapter.checkpoint('failed')
    adapter.release()

def stage(adapter):
    phase=adapter.phase()
    require(phase in PHASES,'STAGING_PHASE_REFUSED')
    adapter.bind()
    if phase=='ready':
        # Do not roll back on a read failure here: acceptance may have begun.
        adapter.verify('new',boot=True)
        return {'code':'STAGING_READY','real_return_verified':True,'deployed':False}
    if phase=='failed':
        adapter.verify('old',boot=True)
        adapter.release()
        return {'code':'STAGING_FAILED','previous_restored':True,'deployed':False}
    if phase=='recovery-required':
        try:restore(adapter)
        except Exception:
            return {'code':'STAGING_RECOVERY_REQUIRED','previous_restored':False,'deployed':False}
        return {'code':'STAGING_FAILED','previous_restored':True,'deployed':False}
    try:
        if phase=='prepared':
            adapter.authorize();replace(adapter,'new')
            adapter.checkpoint('tested');phase='tested'
        if phase=='tested':
            replace(adapter,'old')
            adapter.checkpoint('returned');phase='returned'
        if phase=='returned':
            adapter.authorize();replace(adapter,'new')
            adapter.checkpoint('active');phase='active'
        if phase=='active':
            # A reboot can restore the old persistent generation. Reconcile
            # the inactive slot before changing the boot profile.
            adapter.authorize();replace(adapter,'new')
            adapter.boot('new');adapter.verify('new',boot=True)
            adapter.checkpoint('boot');phase='boot'
        if phase=='boot':
            adapter.authorize();adapter.verify('new',boot=True)
    except Exception:
        # Persist recovery intent before touching the old generation. A crash
        # during restoration must resume restoration, never candidate testing.
        adapter.checkpoint('recovery-required')
        try:restore(adapter)
        except Exception:
            return {'code':'STAGING_RECOVERY_REQUIRED','previous_restored':False,'deployed':False}
        return {'code':'STAGING_FAILED','previous_restored':True,'deployed':False}
    # Outside the rollback handler: a successful durable write with a lost
    # acknowledgement is already visible to a subsequent acceptance worker.
    adapter.checkpoint('ready')
    return {'code':'STAGING_READY','real_return_verified':True,'deployed':False}
