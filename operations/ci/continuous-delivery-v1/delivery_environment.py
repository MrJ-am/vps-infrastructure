"""Read protected code/configuration metadata; never application data or keys."""
import json,os,re
from pathlib import Path
import generation_views as G
import delivery_stack as S
from source_snapshot import require

SLOTS=('blue','green');STAGES=('mirror','review','merge','sync')
PREPARATION='mrjam-delivery-preparation.service'
STAGING='mrjam-delivery-staging.service'

def parse(system,boot,adopted,nginx,units,*,vise_adopted=None,installed_stack=None):
    require(G.store(system) and system==boot and G.store(adopted),'DELIVERY_ENVIRONMENT_NOT_STABLE')
    matches=[slot for slot,port in [('blue',38101),('green',38102)]
        if nginx.count(('127.0.0.1:'+str(port)).encode())==11
        and ('127.0.0.1:'+str(38102 if port==38101 else 38101)).encode() not in nginx]
    require(len(matches)==1,'DELIVERY_ENVIRONMENT_ROUTES_REFUSED')
    state={'schema_version':1,'system':system,'adopted':adopted,'active_slot':matches[0],'slots':{}}
    for slot in SLOTS:
        entries=re.findall(r'^ExecStart=(/nix/store/[^\s]+)/bin/mrjam-server serve --config (/nix/store/[^\s]+)/runtime.json$',
            units['mrjam-rust-'+slot+'.service'],re.M)
        require(len(entries)==1 and all(G.store(p) for p in entries[0]),'DELIVERY_ENVIRONMENT_SLOT_REFUSED')
        state['slots'][slot]=dict(zip(('server','runtime'),entries[0]))
    if PREPARATION in units:
        def package(unit,executable):
            found=re.findall(r'^ExecStart=(/nix/store/[^\s]+)/bin/'+re.escape(executable)+r'$',units[unit],re.M)
            require(len(found)==1 and G.store(found[0]),'DELIVERY_ENVIRONMENT_CONTROL_REFUSED');return found[0]
        preparation=package(PREPARATION,'mrjam-delivery-prepare')
        acceptance={package('mrjam-acceptance-'+stage+'.service','mrjam-acceptance-'+stage) for stage in STAGES}
        require(len(acceptance)==1,'DELIVERY_ENVIRONMENT_MIXED_ACCEPTANCE')
        state['control_plane']={'preparation':preparation,'acceptance':acceptance.pop()}
        if STAGING in units:state['control_plane']['staging']=package(STAGING,'mrjam-delivery-stage')
    require(STAGING not in units or PREPARATION in units,'DELIVERY_ENVIRONMENT_ORPHAN_STAGING')
    if installed_stack is not None:
        path,descriptor=installed_stack
        require(G.store(path),'DELIVERY_ENVIRONMENT_STACK_REFUSED')
        S.verify(descriptor,units,state.get('control_plane'))
        state['control_plane']['stack']=path
    if vise_adopted is not None:
        require(G.store(vise_adopted) and 'vise.service' in units,'DELIVERY_ENVIRONMENT_VISE_REFUSED')
        found=re.findall(r'^ExecStart=(/nix/store/[^\s]+)/server$',units['vise.service'],re.M)
        require(len(found)==1 and G.store(found[0]),'DELIVERY_ENVIRONMENT_VISE_REFUSED')
        state['vise']={'artifact':found[0],'adopted':vise_adopted}
    G.state_checked(state);return state

def read():
    system=os.path.realpath('/run/current-system');boot=os.path.realpath('/nix/var/nix/profiles/system')
    require(G.store(system),'DELIVERY_ENVIRONMENT_SYSTEM_REFUSED')
    names=['mrjam-rust-'+s+'.service' for s in SLOTS]
    stack_link=Path('/etc/mrjam-delivery-stack');installed_stack=None
    if stack_link.exists() or stack_link.is_symlink():
        stack_path=str(stack_link.resolve(strict=True))
        require(G.store(stack_path) and stack_path==str(Path(system,'etc/mrjam-delivery-stack').resolve(strict=True)),
            'DELIVERY_ENVIRONMENT_STACK_DRIFT')
        raw=Path(stack_path,'descriptor.json').read_bytes()
        require(0<len(raw)<=16384,'DELIVERY_ENVIRONMENT_STACK_REFUSED')
        installed_stack=(stack_path,json.loads(raw))
        names.extend(S.UNITS)
    vise_link=Path('/etc/mrjam-vise-delivery-adopted.json');vise_adopted=None
    if vise_link.exists() or vise_link.is_symlink():
        vise_adopted=str(vise_link.resolve(strict=True))
        require(vise_adopted==str(Path(system,'etc/mrjam-vise-delivery-adopted.json').resolve(strict=True)),
            'DELIVERY_ENVIRONMENT_VISE_ADOPTION_DRIFT')
        names.append('vise.service')
    if Path('/etc/systemd/system',PREPARATION).exists():
        names += [PREPARATION]+['mrjam-acceptance-'+s+'.service' for s in STAGES]
    if Path('/etc/systemd/system',STAGING).exists():names.append(STAGING)
    units={}
    for name in dict.fromkeys(names):
        for parent in ('/etc/systemd/system','/run/systemd/system'):
            dropin=Path(parent,name+'.d')
            require(not dropin.exists() or not any(dropin.iterdir()),'DELIVERY_ENVIRONMENT_DROPIN_REFUSED')
        raw=Path('/etc/systemd/system',name).read_bytes()
        require(len(raw)<=65536 and raw==Path(system,'etc/systemd/system',name).read_bytes(),
            'DELIVERY_ENVIRONMENT_UNIT_DRIFT')
        units[name]=raw.decode('utf-8')
    routes=Path('/etc/nginx/nginx.conf').read_bytes()
    require(len(routes)<=1048576 and routes==Path(system,'etc/nginx/nginx.conf').read_bytes(),
        'DELIVERY_ENVIRONMENT_ROUTE_DRIFT')
    adopted=os.path.realpath('/etc/mrjam-delivery-adopted.json')
    require(adopted==os.path.realpath(Path(system,'etc/mrjam-delivery-adopted.json')),'DELIVERY_ENVIRONMENT_ADOPTION_DRIFT')
    return parse(system,boot,adopted,routes,units,vise_adopted=vise_adopted,installed_stack=installed_stack)
