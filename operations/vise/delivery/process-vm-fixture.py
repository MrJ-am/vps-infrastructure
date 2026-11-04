"""VM-only invocation of real fixed adapter process methods; no generation switch."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,os.environ['PROMOTION_PACKAGE']+'/lib')
import promotion_service as S
sys.path.extend([S.RECIPE+'/operations/vise/delivery',S.RECIPE+'/operations/ci/continuous-delivery-v1'])
import transition_adapter as A,process_state as P

adapter=A.Adapter.__new__(A.Adapter)
adapter.key='a'*64
adapter.phase=lambda:os.environ.get('PHASE','prepared')
action=sys.argv[1]
if action=='running':
    first=P.running_identity(os.environ['SYNTHETIC_SERVER']);adapter.health()
    assert first==P.running_identity(os.environ['SYNTHETIC_SERVER'])
    print(json.dumps({'identity_and_health':True}))
elif action=='stop':adapter.stop();adapter.stopped();print('gracefully-stopped')
elif action=='stopped':adapter.stopped();print('stopped')
elif action=='start':adapter.start();adapter.health();print('started')
else:raise ValueError('VM_ACTION_REFUSED')
