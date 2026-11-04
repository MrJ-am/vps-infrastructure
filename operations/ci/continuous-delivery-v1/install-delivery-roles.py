"""Install fixed non-admin delivery identities; secrets stay on the VPS.

No candidate arguments, general API, personal-account changes or branch merge.
The installer restricts existing gates; it never reduces review or status checks.
"""
import fcntl,http.client,importlib.util,json,os,re,stat,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import delivery_roles as R
from source_snapshot import require

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
B=load('bootstrap','/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py')
C=load('credential_helpers','@credential-helpers@')
ROOT=Path('/var/lib/mrjam-delivery-credentials')
C.ROOT=ROOT
C.ACCOUNTS={role:(name,'write:repository',R.APPLICATIONS) for role,name in R.ROLES.items()}

def api(token,method,repository,suffix='',body=None):
    require(repository in R.APPLICATIONS+('mrjam-validation','vps-infrastructure'),'INSTALL_REPOSITORY_REFUSED')
    require((method=='GET' and suffix in ('','/branch_protections/main','/collaborators/MrJam/permission'))
        or (repository in R.APPLICATIONS and method=='PUT' and suffix in
            ['/collaborators/'+name for name in [*R.ROLES.values(),R.HUMAN]] and body=={'permission':'write'})
        or (repository in R.APPLICATIONS and method=='PATCH' and suffix=='/branch_protections/main'
            and type(body) is dict and set(body)=={'enable_merge_whitelist','merge_whitelist_usernames',
                'merge_whitelist_teams','enable_approvals_whitelist','approvals_whitelist_username','approvals_whitelist_teams'}),
        'INSTALL_API_REFUSED')
    connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
    try:
        connection.request(method,'/api/v1/repos/MrJ-am/'+repository+suffix,
            body=None if body is None else json.dumps(body),headers={'Host':'forge.mrj.am',
                'Authorization':'token '+token,'Content-Type':'application/json'})
        response=connection.getresponse();raw=response.read(131073)
        require(len(raw)<=131072,'INSTALL_RESPONSE_LIMIT')
        return response.status,json.loads(raw) if raw else None
    finally:connection.close()

def account(role):
    name=R.ROLES[role];state=C.state(B,name)
    return state,{'name':name,**{key:state[key] for key in ('eligible','organization_memberships','owned_repositories')}}

def acl(role):
    name=R.ROLES[role]
    raw=C.sql(B,f'''SELECT coalesce(json_agg(json_build_object('owner',u.name,'repo',r.name,'permission',c.mode)),'[]'::json)
      FROM collaboration c JOIN repository r ON r.id=c.repo_id JOIN public."user" u ON u.id=r.owner_id
      WHERE c.user_id=(SELECT id FROM public."user" WHERE lower_name='{name}');''')
    return json.loads(raw)

def install():
    require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','INSTALL_HOST_REFUSED')
    require(os.path.realpath('/run/current-system')=='/nix/store/rks6y23zykcka5ifmilxj0p8r6nvrd57-nixos-system-srv1982677-26.05pre-git','INSTALL_BASELINE_REFUSED')
    os.umask(0o077)
    try:ROOT.mkdir(mode=0o700)
    except FileExistsError:pass
    info=ROOT.lstat();require(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0
        and stat.S_IMODE(info.st_mode)==0o700,'INSTALL_STATE_REFUSED')
    journal=ROOT/'provision.json'
    state=json.loads(C.private(journal,0o600)) if journal.exists() else {'schema_version':1,'accounts':{},'protections':{}}
    require({'schema_version','accounts','protections'}<=set(state)<={'schema_version','accounts','protections','human_access','pending_protections'} and state['schema_version']==1
        and set(state['accounts'])<=set(R.ROLES) and set(state['protections'])<=set(R.APPLICATIONS),'INSTALL_JOURNAL_REFUSED')
    state.setdefault('human_access',{});state.setdefault('pending_protections',{})
    require(set(state['human_access'])<=set(R.APPLICATIONS) and set(state['pending_protections'])<=set(R.APPLICATIONS),'INSTALL_JOURNAL_REFUSED')
    with B.governance_lease() as admin:
        before={};plans={}
        for repository in R.APPLICATIONS:
            status,repo=api(admin,'GET',repository)
            require(status==200 and repo.get('full_name')=='MrJ-am/'+repository and not repo.get('has_actions'),
                'INSTALL_REPOSITORY_BOUNDARY_REFUSED')
            status,human=api(admin,'GET',repository,'/collaborators/MrJam/permission')
            require(status==200 and human.get('permission') in ('admin','owner'),'INSTALL_HUMAN_ACCESS_REFUSED')
            status,observed=api(admin,'GET',repository,'/branch_protections/main');require(status==200,'INSTALL_PROTECTION_MISSING')
            if repository in state['protections']:
                require(observed==state['protections'][repository]['after'],'INSTALL_ADOPTED_PROTECTION_MOVED')
            plans[repository]=R.protection_change(repository,observed);before[repository]=observed
        for role,name in R.ROLES.items():
            observed,_=account(role);prior=state['accounts'].get(role)
            if not observed['exists']:
                require(prior is None,'INSTALL_ACCOUNT_DISAPPEARED')
                state['accounts'][role]='creating';C.save(journal,state)
                B.command([B.FORGEJO,'--config',str(B.INI),'admin','user','create','--username',name,
                    '--email',name+'@mrj.am','--random-password','--random-password-length','64','--must-change-password=false'])
            else:require(prior in ('creating','created','ready'),'INSTALL_ACCOUNT_COLLISION')
            observed,identity=account(role)
            require(identity=={'name':name,'eligible':True,'organization_memberships':0,'owned_repositories':0},'INSTALL_ACCOUNT_BOUNDARY_REFUSED')
            state['accounts'][role]='created';C.save(journal,state)
            # Refuse unexpected pre-existing access instead of deleting it.
            existing=acl(role)
            require(all(row in [{'owner':'MrJ-am','repo':r,'permission':2} for r in R.APPLICATIONS] for row in existing),
                'INSTALL_EXISTING_ACL_REFUSED')
            for repository in R.APPLICATIONS:
                require(api(admin,'PUT',repository,'/collaborators/'+name,{'permission':'write'})[0]==204,'INSTALL_GRANT_REFUSED')
            R.verify_acl(role,identity,acl(role))
            path=ROOT/('forgejo-'+role+'-token');label='mrjam-delivery-'+role+'-v1'
            if path.exists():token=C.private(path,0o400).decode().strip()
            else:
                count=C.sql(B,f"SELECT count(*) FROM access_token WHERE uid=(SELECT id FROM public.\"user\" WHERE lower_name='{name}') AND name='{label}';")
                require(count==b'0\n','INSTALL_UNRETAINED_TOKEN_REFUSED')
                token=B.command([B.FORGEJO,'--config',str(B.INI),'admin','user','generate-access-token',
                    '--username',name,'--token-name',label,'--scopes','write:repository','--raw']).decode().strip()
                require(re.fullmatch('[0-9a-f]{40}',token),'INSTALL_TOKEN_FORMAT_REFUSED');C.save(path,(token+'\n').encode(),0o400)
            for forbidden in ('mrjam-validation','vps-infrastructure'):
                require(api(token,'GET',forbidden)[0] in (403,404),'INSTALL_AUTHORITY_NOT_DENIED')
            status,repo=api(token,'GET','mrjam-plateforme')
            require(status==200 and repo.get('permissions')=={'admin':False,'pull':True,'push':True},'INSTALL_WRITE_PERMISSION_REFUSED')
            state['accounts'][role]='ready';C.save(journal,state)
        for repository in R.APPLICATIONS:
            # Forgejo reports global owner access but its whitelist selector
            # still requires explicit repository membership. Preserve the
            # existing owner's review/merge access without changing identity,
            # SSO, password, site-admin role or existing collaboration rights.
            raw=C.sql(B,f'''SELECT to_json(c.mode) FROM collaboration c JOIN repository r ON r.id=c.repo_id
              JOIN public."user" owner ON owner.id=r.owner_id JOIN public."user" person ON person.id=c.user_id
              WHERE owner.name='MrJ-am' AND r.name='{repository}' AND person.name='MrJam';''')
            permission=int(raw.strip()) if raw.strip() else None
            if permission is None:
                state['human_access'].setdefault(repository,{'previous_collaboration':None,'explicit_write_added':False})
                C.save(journal,state)
                require(api(admin,'PUT',repository,'/collaborators/MrJam',{'permission':'write'})[0]==204,'INSTALL_OWNER_MEMBERSHIP_REFUSED')
                state['human_access'][repository]['explicit_write_added']=True;C.save(journal,state)
            else:require(permission>=2,'INSTALL_EXISTING_HUMAN_ACL_REFUSED')
            # Reobserve before restricting; no plan prepared against stale ACL.
            status,current=api(admin,'GET',repository,'/branch_protections/main')
            require(status==200 and current==before[repository],'INSTALL_PROTECTION_MOVED')
            state['pending_protections'].setdefault(repository,{'before':current,'change':plans[repository]});C.save(journal,state)
            require(api(admin,'PATCH',repository,'/branch_protections/main',plans[repository])[0]==200,'INSTALL_PATCH_REFUSED')
            status,after=api(admin,'GET',repository,'/branch_protections/main');require(status==200,'INSTALL_READBACK_REFUSED')
            R.verify_protection(current,after,plans[repository])
            initial=state['protections'].get(repository,state['pending_protections'][repository])['before']
            state['protections'][repository]={'before':initial,'after':after}
            del state['pending_protections'][repository];C.save(journal,state)
    return {'code':'SEPARATE_DELIVERY_IDENTITIES_INSTALLED','accounts':R.ROLES,'application_repositories':7,
        'validation_and_infrastructure_access':False,'site_admin':False,'repository_admin':False,
        'human_access_preserved':True,'temporary_admin_token_revoked':True,'merged':False,'deployed':False}

if __name__=='__main__':
    fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);print(json.dumps(install()))
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'DELIVERY_ROLE_INSTALL_FAILED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
    finally:os.close(fd)
