"""Off-traffic replacement with an exercised return; never changes boot/routes.

The installed adapter preflights signed authority, source acceptance, precise
system generations, immutable artifacts, off-traffic routing and no clients.
"""
def stage(adapter):
    adapter.preflight()
    before=adapter.retained()
    adapter.checkpoint('prepared')
    try:
        for label,target in [('first-stage',adapter.new),('real-return',adapter.old),('final-stage',adapter.new)]:
            adapter.checkpoint(label)
            adapter.no_clients()
            adapter.stop_slot()
            adapter.switch(target)
            adapter.start_slot()
            adapter.verify(target,before)
        adapter.checkpoint('off-traffic-ready-return-verified')
        return {'code':'ACCEPTED_OFF_TRAFFIC_READY','real_return_verified':True,'routes_changed':False,
            'boot_changed':False,'deployed':False}
    except Exception:
        restored=False
        try:
            adapter.no_clients();adapter.stop_slot();adapter.switch(adapter.old);adapter.start_slot()
            adapter.verify(adapter.old,before);restored=True
        except Exception:pass
        adapter.checkpoint('returned-after-failure' if restored else 'recovery-required')
        return {'code':'OFF_TRAFFIC_STAGE_FAILED','previous_restored':restored,'deployed':False}
