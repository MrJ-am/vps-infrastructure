"""Verify retained acceptance evidence on-host; export only closed metadata."""
import sys,json,stat,hashlib
from pathlib import Path
sys.path.insert(0,'/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3/lib')
import contract as C
import signer as A
DIGEST='8177667ea392aacd4c31ae32c03f2e75fd11b15bd716567ad6b412a9cd60defb'
def main():
 policy=C.policy(C.parse(Path(A.POLICY_PATH).read_bytes()))
 path=Path('/var/lib/mrjam-forgejo-runner/attestations')/(DIGEST+'.json')
 m=path.lstat();C.require(stat.S_ISREG(m.st_mode) and m.st_uid==950 and stat.S_IMODE(m.st_mode)==0o400 and m.st_nlink==1,'ATTESTATION_METADATA_REFUSED')
 raw=C.regular_file(path,owner=950,mode=0o400,maximum=C.MAX_DOCUMENT);envelope=C.parse(raw);C.require(A.verify(envelope,policy),'SIGNATURE_REFUSED')
 C.require(envelope['payload']['proposal_sha256']==DIGEST,'PROPOSAL_REFUSED')
 cache=Path('/var/lib/mrjam-validation-collector/authority-v1/artifacts')/DIGEST
 receipt=C.bound_receipt(C.parse(C.regular_file(cache/'receipt.json',owner=952,mode=0o400,maximum=C.MAX_DOCUMENT)),DIGEST,policy['rules_revision'],policy['producer'])
 C.require(envelope['payload']['collector_receipt_sha256']==C.sha(C.canonical(receipt)),'RECEIPT_REFUSED')
 artifacts=[]
 for expected in receipt['artifacts']:
  name=expected['name']
  p=cache/name;m=p.lstat();C.require(stat.S_ISREG(m.st_mode) and m.st_uid==952 and stat.S_IMODE(m.st_mode)==0o400 and m.st_nlink==1 and m.st_size==expected['bytes'],'ARTIFACT_METADATA_REFUSED')
  h=hashlib.sha256()
  with p.open('rb') as f:
   while b:=f.read(1048576):h.update(b)
  artifacts.append({'name':name,'bytes':m.st_size,'sha256':h.hexdigest()})
 C.require(artifacts==receipt['artifacts'],'ARTIFACT_BYTES_REFUSED')
 print(json.dumps({'schema_version':1,'code':'CI_ATTESTATION_VERIFIED','proposal_digest':DIGEST,'rules_revision':policy['rules_revision'],'attestation_sha256':hashlib.sha256(raw).hexdigest(),'key_id':policy['key_id'],'signature_verified':True,'passed_steps':len(envelope['payload']['steps']),'artifacts':artifacts},sort_keys=True))
if __name__=='__main__':
 try:main()
 except (C.Refused,FileNotFoundError) as e:print(json.dumps({'code':str(e) if isinstance(e,C.Refused) else 'ATTESTATION_NOT_PRESENT'}));raise SystemExit(2)
