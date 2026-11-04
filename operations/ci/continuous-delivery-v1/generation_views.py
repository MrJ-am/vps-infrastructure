"""Compare separately evaluated trusted Nix views without weakening the gates.

Views are created by the installed fixed recipe, never supplied by a proposal.
This function checks their input binding and all three generations. It grants
no authority to merge or activate; independent signed delivery checks remain.
"""
import hashlib,json,re
from source_snapshot import require

HEX=re.compile('[0-9a-f]{64}\\Z')
STORE=re.compile('/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+\\Z')
SLOTS={'blue','green'}
FIELDS={'schema_version','phase','candidatePath','input_state_sha256','state','assertions_pass',
    'units','routes_sha256','adopted','slot_services','non_asset_configurations','asset_routes','no_implicit_restart'}

def digest(value):return type(value) is str and HEX.fullmatch(value)
def store(value):return type(value) is str and STORE.fullmatch(value)

def state_checked(state):
    require(type(state) is dict and (set(state)-{'vise'}) in ({'schema_version','system','active_slot','adopted','slots'},
            {'schema_version','system','active_slot','adopted','slots','control_plane'})
        and type(state['schema_version']) is int and state['schema_version']==1
        and store(state['system']) and store(state['adopted']) and state['active_slot'] in SLOTS,
        'GENERATION_STATE_REFUSED')
    if 'vise' in state:
        require(type(state['vise']) is dict and set(state['vise'])=={'artifact','adopted'}
            and all(store(p) for p in state['vise'].values()),'GENERATION_VISE_STATE_REFUSED')
    if 'control_plane' in state:
        require(type(state['control_plane']) is dict and set(state['control_plane']) in
            ({'preparation','acceptance'},{'preparation','acceptance','staging'},
             {'preparation','acceptance','staging','stack'})
            and all(store(v) for v in state['control_plane'].values()),'GENERATION_CONTROL_PLANE_REFUSED')
    require(type(state['slots']) is dict and set(state['slots'])==SLOTS
        and all(type(s) is dict and set(s)=={'runtime','server'} and all(store(p) for p in s.values())
            for s in state['slots'].values()),'GENERATION_SLOTS_REFUSED')

def verify(views,state,state_raw,candidate_path,candidate,bundle):
    state_checked(state)
    require(json.loads(state_raw)==state,'GENERATION_INPUT_STATE_REFUSED')
    require(set(views)=={'current','stage','promotion'} and store(candidate_path),'GENERATION_VIEWS_REFUSED')
    for phase,v in views.items():
        require(type(v) is dict and set(v)==FIELDS and type(v['schema_version']) is int and v['schema_version']==1
            and v['phase']==phase and v['candidatePath']==candidate_path
            and v['input_state_sha256']==hashlib.sha256(state_raw).hexdigest(),'GENERATION_VIEW_BINDING_REFUSED')
        state_checked(v['state'])
        require(type(v['assertions_pass']) is bool and type(v['no_implicit_restart']) is bool
            and digest(v['routes_sha256']) and v['adopted']==v['state']['adopted'],'GENERATION_VIEW_SHAPE_REFUSED')
        require(type(v['units']) is dict and bool(v['units']) and all(type(k) is str and digest(h) for k,h in v['units'].items()),
            'GENERATION_UNIT_VIEW_REFUSED')
        for field in ('slot_services','non_asset_configurations','asset_routes'):
            require(type(v[field]) is dict and set(v[field])==SLOTS and all(digest(h) for h in v[field].values()),
                'GENERATION_SLOT_VIEW_REFUSED')
    a,b,c=(views[k] for k in ('current','stage','promotion'))
    off='green' if state['active_slot']=='blue' else 'blue'
    require(candidate['schema_version']==1 and candidate['deployment_authorized'] is False
        and candidate['slot']==off and digest(candidate['proposal_sha256']) and store(candidate['adopted']) and store(candidate['bundle'])
        and bundle['schema_version']==1 and bundle['deployment_authorized'] is False and bundle['slot']==off
        and bundle['proposal_sha256']==candidate['proposal_sha256']
        and store(bundle['server']) and store(bundle['runtime']),'GENERATION_CANDIDATE_REFUSED')
    staged={**state,'system':b['state']['system'],'slots':{**state['slots'],off:{k:bundle[k] for k in ('server','runtime')}}}
    promoted={**staged,'system':c['state']['system'],'active_slot':off,'adopted':candidate['adopted']}
    require(b['state']==staged and c['state']==promoted,'GENERATION_OUTPUT_STATE_REFUSED')
    def changed(v):return {k for k in a['units'] if a['units'][k]!=v['units'].get(k)}
    checks={
        'currentExact':a['state']==state,
        'assertionsPass':all(v['assertions_pass'] for v in views.values()),
        'stageChangesOnlyOffTraffic':changed(b)<={'mrjam-rust-'+off+'.service'},
        'unitsPreserved':set(a['units'])==set(b['units'])==set(c['units']),
        'stagedRoutesUnchanged':a['routes_sha256']==b['routes_sha256'],
        'stagedAdoptionUnchanged':a['adopted']==b['adopted'],
        'nonAssetConfigurationUnchanged':a['non_asset_configurations']==b['non_asset_configurations']==c['non_asset_configurations'],
        'assetRoutingUnchanged':a['asset_routes']==b['asset_routes']==c['asset_routes'],
        'promotionChangesOnlyRoutesAndBoot':changed(c)<={'nginx.service','nginx-config-reload.service','mrjam-rust-blue.service','mrjam-rust-green.service'},
        'promotionRetainsCommands':b['slot_services']==c['slot_services'],
        'noImplicitRestart':b['no_implicit_restart'] and c['no_implicit_restart']}
    require(all(checks.values()),'GENERATION_INVARIANT_REFUSED')
    return {'schema_version':1,'checks':checks,'current':a['state']['system'],'staged':b['state']['system'],
        'promoted':c['state']['system'],'stagedState':staged,'promotedState':promoted,'deployment_authorized':False}
