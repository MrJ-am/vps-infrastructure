"""Compare fixed-recipe ViSe views without retaining both NixOS evaluations.

These views must come from the protected recipe, not from candidate input.
No activation or signature authority is granted by this comparison.
"""
import hashlib,json,re

HEX=re.compile(r'[0-9a-f]{64}\Z')
STORE=re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+\Z')
FIELDS={'schema_version','profile','phase','candidatePath','input_state_sha256','system','assertions_pass',
    'units','routes','platform_adopted','artifact','adopted','identity_limits','environment','preflight','boot',
    'no_implicit_restart','backup_enabled'}

def require(value):
    if not value:raise ValueError('VISE_GENERATION_VIEW_REFUSED')

def store(value):return type(value) is str and STORE.fullmatch(value)
def digest(value):return type(value) is str and HEX.fullmatch(value)

def verify(views,state_raw,candidate_path,candidate):
    state=json.loads(state_raw)
    require(set(views)=={'current','candidate'} and store(candidate_path))
    for phase,v in views.items():
        require(type(v) is dict and set(v)==FIELDS and type(v['schema_version']) is int and v['schema_version']==1
            and v['profile']=='vise-v1' and v['phase']==phase and v['candidatePath']==candidate_path
            and v['input_state_sha256']==hashlib.sha256(state_raw).hexdigest())
        require(all(v[k] is True for k in ('assertions_pass','no_implicit_restart','backup_enabled')))
        require(all(store(v[k]) for k in ('system','platform_adopted','artifact'))
            and (v['adopted'] is None or store(v['adopted'])))
        require(all(digest(v[k]) for k in ('routes','identity_limits','environment','preflight','boot')))
        require(type(v['units']) is dict and 0<len(v['units'])<=4096
            and all(type(k) is str and digest(h) for k,h in v['units'].items()))
    old,new=views['current'],views['candidate']
    require(old['system']==state['system'] and old['platform_adopted']==state['adopted'])
    if 'vise' in state:
        require({'artifact':old['artifact'],'adopted':old['adopted']}==state['vise'])
    else:require(old['adopted'] is None)
    require(candidate['schema_version']==2 and candidate['profile']=='vise-v1'
        and candidate['deployment_authorized'] is False
        and new['artifact']==candidate['bundle'] and new['adopted']==candidate['adopted'])
    require(set(old['units'])==set(new['units']))
    changed=sorted(k for k in old['units'] if old['units'][k]!=new['units'][k])
    require(set(changed)<={'vise.service'})
    require(all(old[k]==new[k] for k in ('routes','platform_adopted','identity_limits','environment','preflight','boot')))
    return {'schema_version':1,'previous':old['system'],'system':new['system'],'candidate':candidate_path,
        'input_state_sha256':hashlib.sha256(state_raw).hexdigest(),'changed':changed,
        'vise':{'artifact':new['artifact'],'adopted':new['adopted']},'deployment_authorized':False}
