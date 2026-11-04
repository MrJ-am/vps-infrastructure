"""Read-only comparison of built ViSe generations, including all unit links.

No service control, database access, or activation is performed here.
"""
import json,re
from pathlib import Path
import staging_layout as S
from source_snapshot import require

def compare_units(old,new):
    require(set(old)==set(new),'VISE_UNIT_SET_CHANGED')
    changed={name for name in old if old[name]!=new[name]}
    # wantedBy links resolve to the unit's bytes, so their hash changes too.
    require(changed<={'vise.service','multi-user.target.wants/vise.service'},'VISE_OTHER_UNIT_CHANGED')
    return sorted(changed)

def compare_service(old,new,artifact):
    require(S.G.store(artifact),'VISE_ARTIFACT_PATH_REFUSED')
    matches=re.findall(r'^ExecStart=(/nix/store/[^\s]+)/server$',old,re.M)
    require(len(matches)==1 and S.G.store(matches[0]),'VISE_OLD_COMMAND_REFUSED')
    previous=matches[0]
    require(old.count(previous)==2 and previous+'/dist' in old,'VISE_OLD_ARTIFACT_BINDING_REFUSED')
    require(new==old.replace(previous,artifact),'VISE_SERVICE_CONFIGURATION_CHANGED')

def read(path):
    with Path(path).open('rb') as stream:raw=stream.read(1048577)
    require(len(raw)<=1048576,'VISE_LAYOUT_SIZE_REFUSED')
    return raw

def verify(old,new,candidate,*,previous_adopted=None):
    require(all(S.G.store(p) for p in (old,new,candidate)),'VISE_GENERATION_PATH_REFUSED')
    descriptor=json.loads(read(Path(candidate,'descriptor.json')))
    require(descriptor['schema_version']==2 and descriptor['profile']=='vise-v1'
        and descriptor['deployment_authorized'] is False,'VISE_CANDIDATE_PROFILE_REFUSED')
    require(all(S.G.store(descriptor[k]) for k in ('bundle','adopted')),'VISE_CANDIDATE_PATH_REFUSED')
    trees={name:S.inventory(path) for name,path in [('old',old),('new',new)]}
    changed=compare_units(trees['old'],trees['new'])
    compare_service(read(Path(old,'etc/systemd/system/vise.service')).decode(),
        read(Path(new,'etc/systemd/system/vise.service')).decode(),descriptor['bundle'])
    require(read(Path(old,'etc/nginx/nginx.conf'))==read(Path(new,'etc/nginx/nginx.conf')),'VISE_ROUTES_CHANGED')
    adopted=lambda system,name:Path(system,'etc',name).resolve(strict=True)
    require(adopted(old,'mrjam-delivery-adopted.json')==adopted(new,'mrjam-delivery-adopted.json'),
        'VISE_PLATFORM_ADOPTION_CHANGED')
    require(str(adopted(new,'mrjam-vise-delivery-adopted.json'))==descriptor['adopted'],'VISE_ADOPTION_CHANGED')
    prior=Path(old,'etc/mrjam-vise-delivery-adopted.json')
    if previous_adopted is None:
        require(not prior.exists() and not prior.is_symlink(),'VISE_UNEXPECTED_PRIOR_ADOPTION')
    else:
        require(S.G.store(previous_adopted) and str(prior.resolve(strict=True))==previous_adopted,
            'VISE_PRIOR_ADOPTION_CHANGED')
    return {'schema_version':1,'old':old,'new':new,'candidate':candidate,
        'unit_entries':len(trees['old']),'changed':changed,'built_layout_verified':True}
