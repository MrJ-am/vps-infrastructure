"""Fixed local CI accounts and private credentials. No values leave the VPS."""
import importlib.util,json,os,re,stat,sys,http.client,fcntl,signal
from pathlib import Path
ROOT=Path('/var/lib/mrjam-ci-credentials')
BOOTSTRAP='/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py'
REPOS=('Signature','apprendre-a-demontrer','etp-vie-affective','matheval','mrjam-plateforme','mrjam-validation','style-mrjam','vision','vps-infrastructure')
ACCOUNTS={'policy':('mrjam-ci-policy','read:repository',REPOS),'registration':('mrjam-ci-registrar','write:repository',('mrjam-validation',))}
class Refused(Exception):pass
def need(x,code):
 if not x:raise Refused(code)
def private(path,mode):
 s=path.lstat();need(stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==mode,'PRIVATE_FILE_REFUSED');return path.read_bytes()
def save(path,value,mode=0o600):
 data=json.dumps(value,sort_keys=True).encode() if isinstance(value,dict) else value
 tmp=path.with_name(path.name+'.next');fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 try:os.write(fd,data);os.fsync(fd)
 finally:os.close(fd)
 os.replace(tmp,path);d=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY);os.fsync(d);os.close(d)
def sql(B,statement):
 return B.command([B.PSQL,'-X','-w','-qAt','-h','/run/postgresql','-d','forgejo','-v','ON_ERROR_STOP=1'],('BEGIN READ ONLY; SET LOCAL statement_timeout=\'3s\';\n'+statement+'\nROLLBACK;').encode())
def state(B,name):
 need(name in [x[0] for x in ACCOUNTS.values()],'ACCOUNT_REFUSED')
 raw=sql(B,f'''SELECT json_build_object('exists',EXISTS(SELECT FROM public."user" WHERE lower_name='{name}'),
 'eligible',EXISTS(SELECT FROM public."user" WHERE lower_name='{name}' AND name='{name}' AND email='{name}@mrj.am' AND type=0 AND login_type IN (0,1) AND login_source=0 AND coalesce(login_name,'')='' AND NOT is_admin AND is_active AND NOT prohibit_login AND NOT must_change_password AND NOT is_restricted),
 'organization_memberships',(SELECT count(*) FROM org_user WHERE uid=(SELECT id FROM public."user" WHERE lower_name='{name}')),
 'owned_repositories',(SELECT count(*) FROM repository WHERE owner_id=(SELECT id FROM public."user" WHERE lower_name='{name}')));''')
 return json.loads(raw)
def request(token,method,path,body=None):
 base='/api/v1/repos/MrJ-am/'
 allowed=path=='/api/v1/version' or any(path in [base+r,base+r+'/branch_protections/main',base+r+'/collaborators/'+a[0]] for r in REPOS for a in ACCOUNTS.values())
 need(allowed and method in ('GET','PUT','PATCH'),'API_ROUTE_REFUSED')
 headers={'Host':'forge.mrj.am','Authorization':'token '+token,'Accept':'application/json','Content-Type':'application/json','Connection':'close'}
 c=http.client.HTTPConnection('127.0.0.1',3004,timeout=5)
 try:
  c.request(method,path,None if body is None else json.dumps(body),headers);r=c.getresponse();data=r.read(131073);need(len(data)<=131072,'API_LIMIT');return r.status,json.loads(data) if data else None
 finally:c.close()
def permissions(B,token,role):
 name,scope,repos=ACCOUNTS[role]
 for r in repos:
  code,value=request(token,'GET','/api/v1/repos/MrJ-am/'+r+'/branch_protections/main');need(code==200 and value.get('branch_name')=='main','PERMISSION_MISSING')
 # The account has no organization membership, own repository or site-admin role.
 s=state(B,name);need(s['eligible'] and s['organization_memberships']==0 and s['owned_repositories']==0,'ACCOUNT_BOUNDARY_REFUSED')
 raw=sql(B,f'''SELECT coalesce(json_agg(json_build_object('repo',r.name,'permission',c.mode) ORDER BY r.name),'[]'::json) FROM collaboration c JOIN repository r ON r.id=c.repo_id WHERE c.user_id=(SELECT id FROM public."user" WHERE lower_name='{name}');''')
 need(json.loads(raw)==[{'repo':r,'permission':3} for r in sorted(repos)],'REPOSITORY_ACL_REFUSED')
 if role=='registration':need(request(token,'GET','/api/v1/repos/MrJ-am/mrjam-plateforme')[0] in (403,404),'OTHER_REPOSITORY_NOT_DENIED')
 else:
  code,value=request(token,'GET','/api/v1/repos/MrJ-am/mrjam-validation');need(code==200,'READ_REFUSED')
  need(request(token,'PATCH','/api/v1/repos/MrJ-am/mrjam-validation',{'has_actions':value['has_actions']})[0]==403,'WRITE_NOT_DENIED')
def provision(B):
 need(os.geteuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
 need(os.path.realpath('/run/current-system')=='/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git','BASELINE_REFUSED')
 os.umask(0o077)
 if not ROOT.exists():ROOT.mkdir(mode=0o700)
 s=ROOT.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o700,'DIRECTORY_REFUSED')
 journal=ROOT/'provision.json';j=json.loads(private(journal,0o600)) if journal.exists() else {'schema_version':1,'accounts':{}}
 need(set(j)=={'schema_version','accounts'} and j['schema_version']==1 and set(j['accounts'])<=set(ACCOUNTS),'JOURNAL_REFUSED')
 with B.governance_lease() as admin:
  for role,(name,scope,repos) in ACCOUNTS.items():
   s=state(B,name);prior=j['accounts'].get(role)
   if not s['exists']:
    need(prior is None,'ACCOUNT_DISAPPEARED');j['accounts'][role]='creating';save(journal,j)
    B.command([B.FORGEJO,'--config',str(B.INI),'admin','user','create','--username',name,'--email',name+'@mrj.am','--random-password','--random-password-length','64','--must-change-password=false'])
   else:need(prior in ('creating','created','ready'),'ACCOUNT_COLLISION')
   need(state(B,name)['eligible'],'ACCOUNT_NOT_ELIGIBLE');j['accounts'][role]='created';save(journal,j)
   for r in repos:
    code,_=request(admin,'PUT','/api/v1/repos/MrJ-am/'+r+'/collaborators/'+name,{'permission':'admin'});need(code==204,'GRANT_REFUSED')
   path=ROOT/('forgejo-'+role+'-token');label='mrjam-ci-'+role+'-v1'
   if path.exists():token=private(path,0o400).decode().strip()
   else:
    count=sql(B,f"SELECT count(*) FROM access_token WHERE uid=(SELECT id FROM public.\"user\" WHERE lower_name='{name}') AND name='{label}';")
    need(count==b'0\n','UNRETAINED_TOKEN_REQUIRES_RECOVERY')
    token=B.command([B.FORGEJO,'--config',str(B.INI),'admin','user','generate-access-token','--username',name,'--token-name',label,'--scopes',scope,'--raw']).decode().strip()
    need(re.fullmatch('[0-9a-f]{40}',token),'TOKEN_FORMAT');save(path,(token+'\n').encode(),0o400)
   permissions(B,token,role);j['accounts'][role]='ready';save(journal,j)
 return {'schema_version':1,'code':'CI_CREDENTIALS_READY','accounts_non_admin':True,'policy_repositories':9,'registrar_repositories':1,'private_credentials_exported':False,'temporary_token_revoked':True,'ci_activated':False}
def main():
 signal.alarm(240)
 spec=importlib.util.spec_from_file_location('bootstrap',BOOTSTRAP);B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
 lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  result=provision(B);print(json.dumps(result,sort_keys=True));return 0
 except Exception as e:
  print(json.dumps({'schema_version':1,'code':str(e) if isinstance(e,Refused) else 'CI_CREDENTIAL_PREPARATION_REFUSED','ci_activated':False},sort_keys=True));return 1
 finally:os.close(lock)
if __name__=='__main__':raise SystemExit(main())
