"""Publish one actual signed CI result to its exact private GitHub commit."""
import json,os,stat,sys
from pathlib import Path
sys.path.insert(0,'/nix/store/adylyavm0s2y1zjrcpmg0zyklhg3p89d-mrjam-github-proposal-discovery-1/lib')
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
import github_proposals as P
import admission_control as R
import contract as C
import signer as A
HEAD='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
DIGEST='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
BASE='/repos/MrJ-am/mrjam-plateforme'

def main():
    C.require(os.getuid()==0,'ADMIN_REQUIRED')
    policy=R.load(DIGEST)['authority']
    raw=C.regular_file(Path('/var/lib/mrjam-delivery-captures')/DIGEST/'attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT)
    envelope=C.parse(raw)
    C.require(A.verify(envelope,policy) and C.sha(raw)=='645cbd33f82d0be8dbc2eef6990ba854a3610d96476c83dc922265b7f46a1e01','ATTESTATION_REFUSED')
    C.require(any(s['revision']==HEAD and s['repository']=='MrJ-am/mrjam-plateforme' for s in policy['sources']),'SOURCE_REFUSED')
    fd=os.open('/var/lib/mrjam-github-app/app-credentials.json',os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        C.require(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o400 and info.st_size<=32768,'CREDENTIAL_REFUSED')
        credentials=P.A.checked(json.loads(stream.read(32769)))
    permissions={'metadata':'read','pull_requests':'read','statuses':'write'}
    status,created=P.api('/app/installations/'+str(P.INSTALLATION)+'/access_tokens',P.A.jwt(credentials),'POST',{'repository_ids':[1437120781],'permissions':permissions})
    C.require(status==201 and type(created.get('token')) is str,'TOKEN_REFUSED')
    token=created['token']
    try:
        C.require(created['permissions']==permissions,'PERMISSIONS_REFUSED')
        status,pr=P.api(BASE+'/pulls/2',token)
        C.require(status==200 and P.project('mrjam-plateforme',pr)['head']==HEAD,'HEAD_MOVED')
        body={'state':'success','context':'mrjam/independent-validation',
              'description':'74 contrôles réussis ; signature Ed25519 vérifiée',
              'target_url':'https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/2'}
        status,result=P.api(BASE+'/statuses/'+HEAD,token,'POST',body)
        C.require(status==201 and all(result.get(k)==v for k,v in body.items()),'STATUS_NOT_CONFIRMED')
    finally:
        status,_=P.api('/installation/token',token,'DELETE')
        C.require(status==204,'REVOCATION_FAILED')
    print(json.dumps({'code':'REAL_VALIDATION_STATUS_PUBLISHED','head':HEAD,'passed_steps':74,'token_revoked':True,'merged':False,'deployed':False}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,(C.Refused,P.A.Refused)) else 'FEEDBACK_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
