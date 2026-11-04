"""Invented immutable verifier for the IPC/unit proof, not an application test."""
import hashlib,json,os,sys
from pathlib import Path

assert sys.argv[1:]==['/input']
assert not any(Path(p).exists() for p in ['/run/credentials','/run/mrjam-validation-authority','/var/lib/mrjam-validation-collector','/var/lib/mrjam-forgejo-runner'])
manifest=Path('/input/manifest.json').read_bytes()
proposal=hashlib.sha256(manifest).hexdigest()
policy_raw=Path('@report-policy@').read_bytes()
policy=json.loads(policy_raw)
bodies=[b'INVENTED SERVER NOT DEPLOYABLE\n',b'INVENTED FRONTEND NOT DEPLOYABLE\n']
names=['server','frontend.tar','verification.json']
entries=[{'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in zip(names,bodies)]
report={'schema_version':1,'decision':'passed','authority':'local-verifier-content-receipt','independent_adoption_established':False,'production_authorized':False,'proposal_sha256':proposal,'rules_revision':policy['rules_revision'],'policy_sha256':hashlib.sha256(policy_raw).hexdigest(),'steps':[{'name':name,'status':'passed'} for name in policy['required_steps']],'sources':policy['sources'],'artifacts':entries,'not_established':policy['not_established']}
canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':')).encode('ascii')
bodies.append(canonical(report))
entries.append({'name':names[2],'bytes':len(bodies[2]),'sha256':hashlib.sha256(bodies[2]).hexdigest()})
with open('/output/channel','wb',buffering=0) as channel:
    channel.write(canonical({'artifacts':entries})+b'\n')
    for raw in bodies:channel.write(raw)
