"""Compare a built control-stack upgrade with its independently evaluated view.

Read-only: system generations and public code/configuration metadata only.
The expected view is supplied by the protected operator, never by an app PR.
"""
import hashlib,json,re
from pathlib import Path
import staging_layout as L
import delivery_stack as D
from source_snapshot import require

def read(path,maximum=1048576):
    with Path(path).open('rb') as stream:raw=stream.read(maximum+1)
    require(len(raw)<=maximum,'STACK_LAYOUT_SIZE_REFUSED')
    return raw

def one(text,name):
    matches=re.findall('^'+re.escape(name)+'=(.*)$',text,re.M)
    require(len(matches)==1,'STACK_LAYOUT_PROPERTY_REFUSED')
    return matches[0]

def verify(old,expected):
    state=expected['state'];L.G.state_checked(state)
    require(L.G.store(old) and expected['deployment_authorized'] is False
        and bool(expected['checks']) and all(v is True for v in expected['checks'].values()),
        'STACK_LAYOUT_EVALUATION_REFUSED')
    new=state['system'];control=state['control_plane'];stack=control['stack']
    before,after=L.inventory(old),L.inventory(new)
    recovery={'forgejo.service.wants','forgejo.service.wants/mrjam-forgejo-runner.service'}
    require(set(before)<=set(after) and set(after)-set(before)==recovery-set(before),
        'STACK_LAYOUT_UNIT_SET_CHANGED')
    require(after.get('forgejo.service.wants')=='directory'
        and after.get('forgejo.service.wants/mrjam-forgejo-runner.service')==after['mrjam-forgejo-runner.service'],
        'STACK_LAYOUT_RUNNER_RECOVERY_REFUSED')
    changed=sorted(n for n in before if before[n]!=after[n])
    require({n for n in changed if '/' not in n}==set(expected['changed']),
        'STACK_LAYOUT_UNIT_DELTA_CHANGED')
    require(all(n.rsplit('/',1)[-1] in expected['changed'] for n in changed),
        'STACK_LAYOUT_OTHER_UNIT_CHANGED')
    units={n:read(Path(new,'etc/systemd/system',n),65536).decode() for n in expected['units']}
    require(units==expected['units'],'STACK_LAYOUT_EVALUATED_UNITS_CHANGED')
    require(read(Path(old,'etc/nginx/nginx.conf'))==read(Path(new,'etc/nginx/nginx.conf')),
        'STACK_LAYOUT_ROUTES_CHANGED')
    adopted=lambda system,name:str(Path(system,'etc',name).resolve(strict=True))
    require(adopted(old,'mrjam-delivery-adopted.json')==adopted(new,'mrjam-delivery-adopted.json')==state['adopted'],
        'STACK_LAYOUT_ADOPTION_CHANGED')
    for system in (old,new):
        vise=Path(system,'etc/mrjam-vise-delivery-adopted.json')
        if 'vise' in state:
            require(str(vise.resolve(strict=True))==state['vise']['adopted'],'STACK_LAYOUT_VISE_ADOPTION_CHANGED')
        else:require(not vise.exists() and not vise.is_symlink(),'STACK_LAYOUT_VISE_ADOPTION_CHANGED')
    require(adopted(new,'mrjam-delivery-stack')==stack,'STACK_LAYOUT_STACK_CHANGED')
    descriptor=json.loads(read(Path(stack,'descriptor.json'),16384))
    packages=D.verify(descriptor,units,{k:v for k,v in control.items() if k!='stack'})
    binding=json.loads(read(Path(packages['anchor'],'host-binding.json')))
    require(json.loads(read(Path(new,'etc/mrjam-validation-authority/producer.json')))==binding['producer'],
        'STACK_LAYOUT_PRODUCER_CHANGED')
    runner=units['mrjam-forgejo-runner.service']
    command=one(runner,'ExecStart')
    suffix='/bin/forgejo-runner daemon --config %d/runner-config'
    require(command.endswith(suffix) and L.G.store(command[:-len(suffix)]),'STACK_LAYOUT_RUNNER_COMMAND_REFUSED')
    root=one(runner,'RootDirectory');require(L.G.store(root),'STACK_LAYOUT_RUNNER_ROOT_REFUSED')
    executable=command.split(' ',1)[0];client=packages['anchor']+'/bin/mrjam-validation-request-attestation'
    # The qualified Nix package wraps the Go executable to supply pinned Git.
    # Follow only that exact package-local target, never an arbitrary command.
    target=executable.rsplit('/',1)[0]+'/.forgejo-runner-wrapped'
    wrapper=read(executable,65536).decode()
    require(re.findall(r'^exec -a "\$0" "([^"]+)"  "\$@" *$',wrapper,re.M)==[target],
        'STACK_LAYOUT_RUNNER_WRAPPER_CHANGED')
    binary=read(target,268435456)
    require(binary.startswith(b'\x7fELF'),'STACK_LAYOUT_RUNNER_BINARY_REFUSED')
    require(client.encode() in binary,'STACK_LAYOUT_RUNNER_CLIENT_CHANGED')
    for path in (executable,target,client):
        require(hashlib.sha256(read(path,268435456)).digest()==
            hashlib.sha256(read(Path(root,path.lstrip('/')),268435456)).digest(),
            'STACK_LAYOUT_RUNNER_ROOT_CHANGED')
    return {'schema_version':1,'old':old,'new':new,'stack':stack,'unit_entries':len(before),
        'changed':changed,'added':sorted(set(after)-set(before)),
        'built_layout_verified':True,'coordinator_client_verified':True,'coordinator_recovery_verified':True,
        'deployment_authorized':False}
