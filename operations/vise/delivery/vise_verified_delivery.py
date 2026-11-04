"""Read-only reauthorization of a fixed ViSe transition, including live Forgejo.

No merge, activation, database or ledger mutation. The observer identity is
read-only; a pre-existing protected merge is required before merge reconciliation.
"""
import http.client,json
from pathlib import Path
import contract as C,admission_control as A,admission_orchestrator as O,signer
import delivery_profiles as Profiles,generation_views as G,forge_merge as M,validation_dispatch as D
import package_content as P

def read(path,maximum):
    with Path(path).open('rb') as stream:raw=stream.read(maximum+1)
    C.require(len(raw)<=maximum,'VISE_DELIVERY_SIZE_REFUSED')
    return raw

def content(bundle,digest,artifacts):
    C.require(G.store(bundle),'VISE_DELIVERY_BUNDLE_REFUSED');root=Path(bundle)
    manifest=C.parse(read(root/'artifact.json',1048576))
    files=P.frontend(artifacts['frontend.tar'],C.sha(artifacts['frontend.tar']))
    expected={'schema_version':1,'profile':'vise-v1','proposal_sha256':digest,
        'server':manifest.get('server'),'server_sha256':C.sha(artifacts['server']),
        'frontend_archive_sha256':C.sha(artifacts['frontend.tar']),
        'frontend_files':{name:C.sha(raw) for name,raw in files.items()},'deployment_authorized':False}
    C.require(manifest==expected and G.store(manifest['server']),'VISE_DELIVERY_MANIFEST_CHANGED')
    server=Path(manifest['server'])
    C.require((root/'server').is_symlink() and (root/'server').readlink()==server/'bin/mrjam-server',
        'VISE_DELIVERY_EXECUTABLE_CHANGED')
    C.require(read(server/'libexec/mrjam-server',67108864)==artifacts['server'],'VISE_DELIVERY_SERVER_CHANGED')
    dist=root/'dist';C.require(dist.is_dir() and not dist.is_symlink(),'VISE_DELIVERY_DIST_REFUSED')
    names=set();directories={str(p) for name in files for p in Path(name).parents if str(p)!='.'}
    count=0
    for path in dist.rglob('*'):
        count+=1;C.require(count<=16384 and not path.is_symlink(),'VISE_DELIVERY_TREE_REFUSED')
        name=path.relative_to(dist).as_posix()
        if path.is_dir():C.require(name in directories,'VISE_DELIVERY_DIRECTORY_CHANGED');continue
        C.require(path.is_file() and name in files,'VISE_DELIVERY_FILE_CHANGED')
        C.require(read(path,len(files[name]))==files[name],'VISE_DELIVERY_FRONTEND_CHANGED');names.add(name)
    C.require(names==set(files),'VISE_DELIVERY_FRONTEND_MISSING')
    return manifest

def verify(plan,token,*,jobs=Path('/var/lib/mrjam-intake-admission/jobs')):
    C.require(plan.get('profile')=='vise-v1' and G.digest(plan.get('job'))
        and G.digest(plan.get('proposal_sha256')) and G.store(plan.get('candidate')),
        'VISE_DELIVERY_PLAN_REFUSED')
    root=O.W.private_directory(jobs/plan['job']);job=O.read(root/'state.json')
    proposal=job['capture']['proposal'];digest=plan['proposal_sha256']
    C.require(job['id']==plan['job'] and job['phase'] in {'validated','deployed'}
        and Profiles.selected(proposal)=='vise' and job['capture']['proposal_sha256']==digest,
        'VISE_DELIVERY_JOB_CHANGED')
    selected=A.load(digest);policy=selected['authority']
    C.require(selected['details'].get('profile')=='vise-v1','VISE_DELIVERY_AUTHORITY_PROFILE_REFUSED')
    envelope=C.parse(C.regular_file(root/'artifacts/attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT))
    C.require(signer.verify(envelope,policy) and envelope['payload']['proposal_sha256']==digest,
        'VISE_DELIVERY_SIGNATURE_REFUSED')
    rows=envelope['payload']['artifacts'];artifacts={}
    C.require(len(rows)==3 and {item['name'] for item in rows}=={'server','frontend.tar','verification.json'},
        'VISE_DELIVERY_ARTIFACT_SET_REFUSED')
    for item in rows:
        raw=C.regular_file(root/'artifacts'/item['name'],owner=0,mode=0o400,maximum=dict(C.ARTIFACTS)[item['name']])
        C.require(len(raw)==item['bytes'] and C.sha(raw)==item['sha256'],'VISE_DELIVERY_SIGNED_BYTES_CHANGED')
        artifacts[item['name']]=raw
    candidate=C.parse(read(Path(plan['candidate'])/'descriptor.json',65536))
    C.require(candidate['schema_version']==2 and candidate['profile']=='vise-v1'
        and candidate['deployment_authorized'] is False and candidate['proposal_sha256']==digest
        and candidate['bundle']==plan['bundle'] and candidate['adopted']==plan['adopted']
        and candidate['verification_sha256']==C.sha(artifacts['verification.json'])
        and candidate['policy']==selected['details']['report_policy'],'VISE_DELIVERY_CANDIDATE_CHANGED')
    C.require(all(G.store(candidate[k]) for k in ('bundle','adopted','policy','source')),
        'VISE_DELIVERY_CANDIDATE_PATH_REFUSED')
    C.require(C.sha(read(Path(candidate['source'])/'manifest.json',1048576))==digest,
        'VISE_DELIVERY_SOURCE_MANIFEST_CHANGED')
    C.require(C.parse(read(candidate['adopted'],65536))=={'schema_version':1,
        'source':candidate['source'],'policy':candidate['policy'],'proposal_sha256':digest},
        'VISE_DELIVERY_ADOPTION_CHANGED')
    C.require(C.sha(read(candidate['policy'],1048576))==policy['report_policy_sha256'],
        'VISE_DELIVERY_POLICY_CHANGED')
    sources=[s for s in policy['sources'] if s['repository']=='MrJ-am/'+proposal['repository'] and s['revision']==proposal['head']]
    C.require(len(sources)==1,'VISE_DELIVERY_SOURCE_CHANGED')
    manifest=content(plan['bundle'],digest,artifacts)
    number=plan['forge_pull'];C.require(type(number) is int and number>0,'VISE_DELIVERY_PULL_REFUSED')
    api=M.API(proposal,number,token,token)
    C.require(api('GET','/pulls/'+str(number)).get('merged') is True,'VISE_DELIVERY_MERGE_REQUIRED')
    identifier=job['run']['id'];C.require(type(identifier) is int and identifier>0,'VISE_DELIVERY_RUN_REFUSED')
    connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
    try:
        connection.request('GET',D.BASE+'/actions/runs/'+str(identifier),headers={'Host':'forge.mrj.am','Authorization':'token '+token})
        response=connection.getresponse();raw=response.read(1048577)
        C.require(response.status==200 and len(raw)<=1048576,'VISE_DELIVERY_RUN_OBSERVATION_REFUSED');row=json.loads(raw)
    finally:connection.close()
    C.require(row.get('id')==identifier,'VISE_DELIVERY_RUN_CHANGED')
    run=D.identify(row,digest,policy['rules_revision'])
    C.require(run is not None and run['terminal'] is True and run['status']=='success','VISE_DELIVERY_RUN_NOT_SUCCESSFUL')
    def readonly(method,suffix,body=None):
        C.require(method=='GET','VISE_DELIVERY_REMOTE_WRITE_REFUSED');return api(method,suffix,body)
    M.merge(proposal,number,run,policy,envelope,plan['review'],readonly,verify=signer.verify)
    return manifest
