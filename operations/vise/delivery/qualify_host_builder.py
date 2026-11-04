"""Fixed preparation-only qualification; no candidate activation or SQL access."""
import fcntl,json,os,sys
from pathlib import Path

RECIPE=Path('/nix/store/8gk2n61387dfpbi83bkb2vvjhncjc5yf-mrjam-protected-delivery-recipe-1')
STATE=Path('/nix/store/7f18jjs3rx58w2ixah22ykwqw3s85d4m-vise-delivery-host-state-001.json')
CANDIDATE='/nix/store/51bx822kblj1a93pxnmqqwjiyxnbqf68-mrjam-vise-delivery-candidate-8ea736fc4819'
WORK=Path('/var/lib/mrjam-vise-generation-qualification-001')
NIX='/nix/store/b8y93ncn8bqndj3iid6lla4hvjhhy9ps-nix-2.34.8/bin/'
sys.path[:0]=[str(RECIPE/'operations/vise/delivery'),str(RECIPE/'operations/ci/continuous-delivery-v1'),
 '/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib',
 '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib']
import host_builder as H

def observe():
    current=os.path.realpath('/run/current-system')
    H.B.require(current==os.path.realpath('/nix/var/nix/profiles/system'),'QUALIFICATION_BOOT_CHANGED')
    return current

def main():
    H.B.require(os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1,'QUALIFICATION_HOST_REFUSED')
    H.B.require(os.environ.get('STATE_DIRECTORY')==str(WORK),'QUALIFICATION_DIRECTORY_REFUSED')
    state=json.loads(STATE.read_bytes())
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=H.Builder(RECIPE/'operations/vise/delivery/generations.nix',NIX+'nix-instantiate',NIX+'nix-build').construct(
            WORK,state,CANDIDATE,observe=observe)
    print(json.dumps({'schema_version':1,'scope':'synthetic candidate generation preparation only',
        'result':result,'production_activated':False,'candidate_authority_established':False},sort_keys=True))

if __name__=='__main__':main()
