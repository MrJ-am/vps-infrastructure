"""Restartable single-writer ViSe replacement after protected acceptance.

The installed adapter owns the shared lock, immutable plan, signature/merge
checks and durable journal. stop() must prove that the previous process exited
gracefully before switch/start. Neither direction restores SQL or a ledger.
"""
PHASES={'prepared','new-tested','returned','active','boot','commit-ready','complete','recovering','failed'}

def replace(adapter,target):
    adapter.stop()
    adapter.stopped()
    adapter.switch(target)
    adapter.start()
    adapter.verify(target,boot=False)

def recover(adapter):
    # Intent must be durable before recovery mutates runtime or boot state.
    # Repeating recovery after process death never requires candidate authority.
    adapter.checkpoint('recovering')
    try:
        replace(adapter,'old')
        adapter.boot('old');adapter.verify('old',boot=True)
        adapter.abort_job()
        adapter.checkpoint('failed')
    except Exception:
        return {'code':'VISE_RECOVERY_REQUIRED','previous_restored':False}
    return {'code':'VISE_FAILED','previous_restored':True}

def promote(adapter):
    phase=adapter.phase()
    if phase not in PHASES:raise ValueError('VISE_TRANSITION_PHASE_REFUSED')
    adapter.bind()
    if phase=='complete':
        adapter.verify_complete();return {'code':'VISE_COMPLETE','recovered':True}
    if phase=='failed':
        adapter.verify('old',boot=True);return {'code':'VISE_FAILED','previous_restored':True}
    adapter.reserve()
    if phase=='recovering':return recover(adapter)
    try:
        if phase=='prepared':
            adapter.authorize();replace(adapter,'new')
            adapter.checkpoint('new-tested');phase='new-tested'
        if phase=='new-tested':
            replace(adapter,'old')
            adapter.checkpoint('returned');phase='returned'
        if phase=='returned':
            adapter.authorize();replace(adapter,'new')
            adapter.checkpoint('active');phase='active'
        if phase=='active':
            # A reboot can have restored the old boot generation.
            adapter.authorize();replace(adapter,'new')
            adapter.boot('new');adapter.verify('new',boot=True)
            adapter.checkpoint('boot');phase='boot'
        if phase=='boot':
            adapter.authorize();adapter.verify('new',boot=True)
            adapter.checkpoint('commit-ready');phase='commit-ready'
    except Exception:
        return recover(adapter)
    # A lost receipt-write response must never roll back a possibly committed
    # delivery. Completion is reconciled separately under the same reservation.
    if phase=='commit-ready':
        adapter.verify('new',boot=True)
        adapter.commit_job();adapter.checkpoint('complete')
    return {'code':'VISE_COMPLETE','recovered':False}
