"""Restartable promotion protocol behind the shared environment lock.

The installed adapter owns immutable plans, durable writes and all authority,
runtime and boot checks. A journal phase denotes only completed observations.
Operations between checkpoints must be idempotent. Process death (BaseException
in tests) leaves the last durable phase, never an invented success.
"""
from source_snapshot import require

PHASES={'prepared','new-tested','returned','active','boot','commit-ready','complete','failed','recovery-required'}

def promote(adapter):
    phase=adapter.phase()
    require(phase in PHASES,'PROMOTION_PHASE_REFUSED')
    if phase=='complete':
        adapter.verify_complete()
        return {'code':'PROMOTION_COMPLETE','recovered':True}
    if phase in {'failed','recovery-required'}:
        return {'code':'PROMOTION_RECOVERY_REQUIRED' if phase=='recovery-required' else 'PROMOTION_FAILED'}
    # Durable root job reservation is checked before observing a moved base or
    # performing any external action. Creating it follows a durable plan write.
    adapter.reserve()
    try:
        if phase=='prepared':
            adapter.authorize();adapter.ready('new');adapter.switch('new');adapter.verify('new',boot=False)
            adapter.checkpoint('new-tested');phase='new-tested'
        if phase=='new-tested':
            adapter.ready('old');adapter.switch('old');adapter.verify('old',boot=False)
            adapter.checkpoint('returned');phase='returned'
        if phase=='returned':
            adapter.authorize();adapter.ready('new');adapter.switch('new');adapter.verify('new',boot=False)
            adapter.checkpoint('active');phase='active'
        if phase=='active':
            # Reobserve after a reboot before changing the persistent profile.
            adapter.authorize();adapter.ready('new');adapter.switch('new');adapter.verify('new',boot=False)
            adapter.boot('new');adapter.verify('new',boot=True)
            adapter.checkpoint('boot');phase='boot'
        if phase=='boot':
            adapter.authorize();adapter.ready('new');adapter.verify('new',boot=True)
            # Durable evidence precedes the final job write. From this point
            # a storage error may have committed the job already: never undo
            # the live deployment on an ambiguous receipt-write outcome.
            adapter.checkpoint('commit-ready');phase='commit-ready'
    except Exception:
        # Ordinary operation failures return to the previous compatible live
        # generation. Reservation survives if recovery itself cannot be proved.
        restored=False
        try:
            adapter.ready('old');adapter.switch('old');adapter.boot('old');adapter.verify('old',boot=True)
            adapter.abort_job();restored=True
        except Exception:pass
        adapter.checkpoint('failed' if restored else 'recovery-required')
        return {'code':'PROMOTION_FAILED','previous_restored':restored}
    if phase=='commit-ready':
        adapter.verify('new',boot=True)
        adapter.commit_job();adapter.checkpoint('complete')
    return {'code':'PROMOTION_COMPLETE','recovered':False}
