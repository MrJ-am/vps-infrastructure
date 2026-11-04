"""Verify the complete built systemd tree, including masks and drop-ins."""
import hashlib,re
from pathlib import Path
import generation_views as G
from source_snapshot import require

def inventory(system):
    require(G.store(system),'STAGING_SYSTEM_PATH_REFUSED')
    root=Path(system,'etc/systemd/system');result={}
    require((Path(system)/'bin/switch-to-configuration').is_file(),'STAGING_GENERATION_NOT_BUILT')
    for count,path in enumerate(root.rglob('*'),1):
        require(count<=4096,'STAGING_UNIT_TREE_TOO_LARGE')
        name=path.relative_to(root).as_posix()
        if path.is_dir():
            require(not path.is_symlink(),'STAGING_UNIT_DIRECTORY_ALIAS_REFUSED')
            result[name]='directory';continue
        resolved=str(path.resolve())
        if resolved=='/dev/null':result[name]='masked';continue
        require(resolved.startswith('/nix/store/') and path.is_file(),'STAGING_UNIT_TARGET_REFUSED')
        with path.open('rb') as stream:raw=stream.read(65537)
        require(len(raw)<=65536,'STAGING_UNIT_TOO_LARGE')
        result[name]=hashlib.sha256(raw).hexdigest()
    require(bool(result),'STAGING_UNIT_TREE_EMPTY');return result

def compare(trees,slot):
    require(set(trees)=={'old','staged','promoted'} and slot in G.SLOTS,'STAGING_LAYOUT_SCOPE_REFUSED')
    old,staged,promoted=(trees[k] for k in ('old','staged','promoted'))
    changes=lambda a,b:{n for n in set(a)|set(b) if a.get(n)!=b.get(n)}
    require(changes(old,staged)<={'mrjam-rust-'+slot+'.service'},'STAGING_BUILT_UNIT_CHANGED')
    allowed={'nginx.service','nginx-config-reload.service','mrjam-rust-blue.service','mrjam-rust-green.service'}
    allowed |= {'multi-user.target.wants/'+name for name in allowed}
    require(changes(staged,promoted)<=allowed,'STAGING_PROMOTION_UNIT_CHANGED')

def verify(old,staged,promoted,slot):
    states={'old':old,'staged':staged,'promoted':promoted}
    for state in states.values():G.state_checked(state)
    trees={k:inventory(v['system']) for k,v in states.items()};compare(trees,slot)
    routes={k:Path(v['system'],'etc/nginx/nginx.conf').read_bytes() for k,v in states.items()}
    public=b'127.0.0.1:'+str(38101 if old['active_slot']=='blue' else 38102).encode()
    candidate=b'127.0.0.1:'+str(38101 if slot=='blue' else 38102).encode()
    require(routes['old']==routes['staged'] and routes['old'].count(public)==11 and candidate not in routes['old']
        and routes['staged'].replace(public,candidate)==routes['promoted'],'STAGING_BUILT_ROUTE_CHANGED')
    for state in states.values():
        require(str(Path(state['system'],'etc/mrjam-delivery-adopted.json').resolve())==state['adopted'],
            'STAGING_BUILT_ADOPTION_CHANGED')
        if 'vise' in state:
            require(str(Path(state['system'],'etc/mrjam-vise-delivery-adopted.json').resolve(strict=True))==state['vise']['adopted'],
                'STAGING_BUILT_VISE_ADOPTION_CHANGED')
            text=Path(state['system'],'etc/systemd/system/vise.service').read_text()
            require(re.findall(r'^ExecStart=(.*)$',text,re.M)==[state['vise']['artifact']+'/server'],
                'STAGING_BUILT_VISE_COMMAND_CHANGED')
        for name,binding in state['slots'].items():
            text=Path(state['system'],'etc/systemd/system/mrjam-rust-'+name+'.service').read_text()
            commands=re.findall(r'^ExecStart=(.*)$',text,re.M)
            require(commands==[binding['server']+'/bin/mrjam-server serve --config '+binding['runtime']+'/runtime.json'],
                'STAGING_BUILT_COMMAND_CHANGED')
    for name in G.SLOTS:
        texts=[Path(s['system'],'etc/systemd/system/mrjam-rust-'+name+'.service').read_text() for s in (staged,promoted)]
        sections=[t.split('[Service]\n',1)[1].split('\n[',1)[0].rstrip() for t in texts]
        require(sections[0]==sections[1],'STAGING_PROMOTION_SERVICE_CHANGED')
    return {'schema_version':1,'units':{k:len(v) for k,v in trees.items()},'built_layout_verified':True}
