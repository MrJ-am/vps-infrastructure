"""Verify captured signed bytes and canonical acceptance for a root delivery plan."""
import http.client,json,re
from pathlib import Path
import contract as C,admission_control as A,signer,admission_orchestrator as O
import forge_merge as M,validation_dispatch as D,delivery_frontends as F
STORE=re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+\Z')

def verify(plan,token):
    C.require(type(plan['job']) is str and re.fullmatch('[0-9a-f]{64}',plan['job']),'DELIVERY_JOB_REFUSED')
    C.require(type(plan['bundle']) is str and STORE.fullmatch(plan['bundle']),'DELIVERY_BUNDLE_PATH_REFUSED')
    root=Path('/var/lib/mrjam-intake-admission/jobs')/plan['job']
    value=O.read(root/'state.json');proposal=value['capture']['proposal'];digest=plan['proposal_sha256']
    C.require(value['phase'] in {'validated','deployed'} and value['capture']['proposal_sha256']==digest,'DELIVERY_JOB_BINDING_REFUSED')
    selected=A.load(digest);policy=selected['authority']
    envelope=C.parse(C.regular_file(root/'artifacts/attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT))
    C.require(signer.verify(envelope,policy) and envelope['payload']['proposal_sha256']==digest,'DELIVERY_SIGNATURE_REFUSED')
    artifacts={}
    for item in envelope['payload']['artifacts']:
        raw=C.regular_file(root/'artifacts'/item['name'],owner=0,mode=0o400,maximum=dict(C.ARTIFACTS)[item['name']])
        C.require(len(raw)==item['bytes'] and C.sha(raw)==item['sha256'],'DELIVERY_CAPTURE_CHANGED');artifacts[item['name']]=raw
    bundle=C.parse(Path(plan['bundle'],'descriptor.json').read_bytes())
    C.require(bundle['proposal_sha256']==digest and bundle['slot']==plan['slot']
        and all(STORE.fullmatch(bundle[k]) for k in ['server','runtime','frontends']),'DELIVERY_BUNDLE_REFUSED')
    C.require(Path(bundle['server'],'libexec/mrjam-server').read_bytes()==artifacts['server'],'DELIVERY_SERVER_CHANGED')
    raw=Path(selected['details']['report_policy']).read_bytes()
    C.require(C.sha(raw)==policy['report_policy_sha256'],'DELIVERY_REPORT_POLICY_CHANGED')
    report=C.parse(raw);sources={s['id']:s['revision'] for s in report['sources']}
    files=F.validate(artifacts['frontend.tar'],archive_sha256=C.sha(artifacts['frontend.tar']),proposal=digest,sources=sources,
        styles={f['id']:sources[f['style_source']] for f in report['frontends']},
        toolchains_sha256='27c05033dd0a7347ccdba0afb4caed5bb359eaeeeb1dd1fedb92ef8dc5701eae')
    inventory=C.parse(Path(bundle['frontends'],'inventory.json').read_bytes())
    for group,entries in files.items():
        folder=Path(inventory['outputs'][group]['store_path'])
        C.require(STORE.fullmatch(str(folder)) and {p.relative_to(folder).as_posix() for p in folder.rglob('*') if not p.is_dir()}==set(entries),'DELIVERY_FRONTEND_INVENTORY_CHANGED')
        C.require(all(not (folder/name).is_symlink() and (folder/name).read_bytes()==data for name,data in entries.items()),'DELIVERY_FRONTEND_CHANGED')
    api=M.API(proposal,plan['forge_pull'],token,token)
    C.require(api('GET','/pulls/'+str(plan['forge_pull'])).get('merged') is True,'DELIVERY_PROTECTED_MERGE_REQUIRED')
    identifier=value['run']['id'];c=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
    try:
        c.request('GET',D.BASE+'/actions/runs/'+str(identifier),headers={'Host':'forge.mrj.am','Authorization':'token '+token})
        response=c.getresponse();raw=response.read(1048577)
        C.require(response.status==200 and len(raw)<=1048576,'DELIVERY_RUN_OBSERVATION_REFUSED');row=json.loads(raw)
    finally:c.close()
    C.require(row.get('id')==identifier,'DELIVERY_RUN_CHANGED')
    run=D.identify(row,digest,policy['rules_revision']);C.require(run is not None,'DELIVERY_RUN_BINDING_REFUSED')
    M.merge(proposal,plan['forge_pull'],run,policy,envelope,plan['review'],api,verify=signer.verify)
    return bundle
