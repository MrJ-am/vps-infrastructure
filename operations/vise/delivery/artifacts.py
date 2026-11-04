"""Bounded content receipts for the existing protected three-artifact protocol.

This module does not sign, adopt, publish, or authorize production deployment.
It is called only after the verifier's build and synthetic runtime stages.
"""
import hashlib,io,json,stat,tarfile
from pathlib import Path
import authority_profile as A,source_policy as P

LIMITS=(('server',64*1024**2),('frontend.tar',64*1024**2),('verification.json',65536))

def prepare(build,output):
    output=Path(output)
    P.require(stat.S_ISDIR(output.lstat().st_mode),'VISE_OUTPUT_DIRECTORY_REFUSED')
    P.require(build.steps==[{'name':name,'status':'passed'} for name in A.REQUIRED_STEPS[:-1]],
        'VISE_INCOMPLETE_VALIDATION')
    server=P.read(build.server,64*1024**2)
    P.require(server[:4]==b'\x7fELF','VISE_SERVER_ARTIFACT_REFUSED')
    with (output/'server').open('xb') as stream:stream.write(server)
    P.require(stat.S_ISDIR(build.dist.lstat().st_mode),'VISE_FRONTEND_ARTIFACT_REFUSED')
    total=count=0
    with (output/'frontend.tar').open('xb') as stream:
        with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            for path in sorted(build.dist.rglob('*')):
                info=path.lstat();count+=1
                P.require(count<=4096,'VISE_FRONTEND_ARTIFACT_LIMIT')
                P.require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),'VISE_FRONTEND_ARTIFACT_REFUSED')
                if stat.S_ISDIR(info.st_mode):continue
                raw=P.read(path,64*1024**2);total+=len(raw)
                P.require(total<=64*1024**2,'VISE_FRONTEND_ARTIFACT_LIMIT')
                entry=tarfile.TarInfo(P.relative(str(path.relative_to(build.dist))))
                entry.size=len(raw);entry.mode=0o444;entry.mtime=0
                archive.addfile(entry,io.BytesIO(raw))
    descriptions=[]
    for name,limit in LIMITS[:2]:
        raw=P.read(output/name,limit)
        descriptions.append({'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    steps=[*build.steps,{'name':A.REQUIRED_STEPS[-1],'status':'passed'}]
    policy=P.checked_policy(build.policy)
    report={'schema_version':1,'decision':'passed','authority':'local-verifier-content-receipt',
        'independent_adoption_established':False,'production_authorized':False,
        'proposal_sha256':build.proposal,'rules_revision':policy['rules_revision'],
        'policy_sha256':P.sha(Path(build.runtime['policy'])),'steps':steps,
        'sources':[{k:s[k] for k in ['id','repository','revision','tree_sha']} for s in policy['sources']],
        'artifacts':descriptions,'not_established':list(A.NOT_ESTABLISHED)}
    raw=(json.dumps(report,sort_keys=True,separators=(',',':'))+'\n').encode()
    P.require(len(raw)<=65536,'VISE_REPORT_LIMIT')
    with (output/'verification.json').open('xb') as stream:stream.write(raw)
    descriptions.append({'name':'verification.json','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    build.steps=steps
    return descriptions

def send(build):
    output=Path('/output');channel=output/'channel'
    P.require(stat.S_ISFIFO(channel.lstat().st_mode),'VISE_COLLECTOR_CHANNEL_REQUIRED')
    descriptions=prepare(build,output)
    def write(stream,raw):
        view=memoryview(raw)
        while view:
            n=stream.write(view);P.require(type(n) is int and n>0,'VISE_COLLECTOR_CLOSED');view=view[n:]
    with channel.open('wb',buffering=0) as stream:
        write(stream,json.dumps({'artifacts':descriptions},separators=(',',':')).encode()+b'\n')
        for item in descriptions:
            with (output/item['name']).open('rb') as source:
                while raw:=source.read(65536):write(stream,raw)
