"""Closed bootstrap capture: signed code only, no activation or credentials."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,'@capture-lib@')
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
import admission_control as R
import contract as C
import signer as A
from delivery_capture import capture,directory

PROPOSAL='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
PARENT=Path('/var/lib/mrjam-delivery-captures')

def main():
    C.require(os.getuid()==0 and len(sys.argv)==1,'INVOCATION_REFUSED')
    policy=R.load(PROPOSAL)['authority']
    PARENT.mkdir(mode=0o700,exist_ok=True)
    fd=directory(PARENT,0);os.close(fd)
    result=capture(PROPOSAL,policy,PARENT/PROPOSAL,
        attestations='/var/lib/mrjam-forgejo-runner/attestations',
        cache='/var/lib/mrjam-validation-collector/authority-v1/artifacts',
        contract=C,verify=A.verify)
    print(json.dumps({'code':'SIGNED_CODE_CAPTURED',**result},sort_keys=True))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,C.Refused):
        print(json.dumps({'code':'DELIVERY_CAPTURE_REFUSED'}));raise SystemExit(2)
