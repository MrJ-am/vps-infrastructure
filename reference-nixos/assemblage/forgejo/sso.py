#!/usr/bin/env python3
"""Reconcile one native OIDC source; no personal IdP credential is recovered.

Secrets stay in root-only runtime state and PostgreSQL stdin, never argv/journal.
The existing native Kanidm operator is used only for its technical idm_admin.
"""
import importlib.util,json,os,pathlib,pwd,re,subprocess,sys,tempfile,time,urllib.request,uuid
P=pathlib.Path

def run(args,*,input=None):
 r=subprocess.run([str(a) for a in args],input=input,capture_output=True,text=True,timeout=90)
 if r.returncode:
  (STATE/'private-error.log').write_text(r.stderr+'\n'+r.stdout)
  raise RuntimeError('Forgejo identity command failed: '+P(str(args[0])).name)
 return r.stdout.strip()

def literal(value):return "'"+str(value).replace("'","''")+"'"

def sql(text):
 return run(['runuser','-u','postgres','--',PG+'/bin/psql','-XAtq','--set=ON_ERROR_STOP=1','-h','/run/postgresql','-d','forgejo'],input=text)

def cli(*args):
 return run(['runuser','-u','forgejo','--','env','FORGEJO_WORK_DIR=/var/lib/forgejo','FORGEJO_CUSTOM=/var/lib/forgejo/custom',FORGEJO,'--config',INI,*args])

def native_client():
 target=STATE/'client.json'
 if target.exists():return json.loads(target.read_text())
 spec=importlib.util.spec_from_file_location('kanidm_operator',LIB)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 api=module.KanidmPrive(KANIDM,'/etc/kanidm/server.toml',CURL,diagnostic=STATE/'kanidm-private.log')
 with tempfile.TemporaryDirectory(prefix='operator-',dir=STATE) as directory:
  # Native private administrative socket; never recover the owner's identity.
  token=api.login('idm_admin',api.recuperer('idm_admin'),directory)
  try:
   group=api.http('/v1/group/mrjam-proprietaire-policy',token=token)['attrs']
   members=group.get('member',[])
   if len(members)!=1:raise RuntimeError('Owner policy must identify exactly one existing identity')
   member=members[0]
   if '@' in member:member=member.split('@',1)[0]
   person=api.http('/v1/person/'+member,token=token)['attrs']
   subject=person['uuid'][0]
   if not re.fullmatch('[0-9a-f-]{36}',subject):raise RuntimeError('Invalid native owner UUID')
   clients=api.http('/v1/oauth2',token=token)
   existing=[v for v in clients if v['attrs'].get('name')==['mrjam-forgejo']]
   if not existing:
    api.http('/v1/oauth2/_basic',{'attrs':{'name':['mrjam-forgejo'],'displayname':['Forgejo'],'oauth2_rs_origin_landing':['https://forge.mrj.am/'],'oauth2_strict_redirect_uri':['true']}},token=token)
   api.http('/v1/oauth2/mrjam-forgejo/_attr/oauth2_rs_origin',['https://forge.mrj.am/user/oauth2/Kanidm/callback'],token=token)
   api.http('/v1/oauth2/mrjam-forgejo/_attr/oauth2_strict_redirect_uri',['true'],token=token)
   api.http('/v1/oauth2/mrjam-forgejo/_attr/oauth2_prefer_short_username',['true'],token=token)
   api.http('/v1/oauth2/mrjam-forgejo/_scopemap/idm_all_persons',['openid','profile','email'],token=token)
   checked=api.http('/v1/oauth2/mrjam-forgejo',token=token)['attrs']
   if checked.get('oauth2_rs_origin')!=['https://forge.mrj.am/user/oauth2/Kanidm/callback'] or checked.get('oauth2_strict_redirect_uri')!=['true'] or checked.get('oauth2_allow_insecure_client_disable_pkce',['false'])!=['false']:
    raise RuntimeError('Unexpected client redirect or PKCE policy')
   secret=api.http('/v1/oauth2/mrjam-forgejo/_basic_secret',token=token)
   if not isinstance(secret,str) or len(secret)<20:raise RuntimeError('Native client secret missing')
   result={'clientId':'mrjam-forgejo','clientSecret':secret,'ownerSubject':subject}
   tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(result));tmp.chmod(0o600);tmp.replace(target)
   return result
  finally:
   api.commande('disable-account','idm_admin')

def prepare():
 global INI
 data=native_client()
 user=pwd.getpwnam('forgejo');home=P('/var/lib/forgejo')
 if not home.exists():home.mkdir(mode=0o750);os.chown(home,user.pw_uid,user.pw_gid)
 directory=home/'.identity-config';directory.mkdir(mode=0o700,exist_ok=True);os.chown(directory,user.pw_uid,user.pw_gid)
 runtime=directory/'app.ini';runtime.write_bytes(P(INI).read_bytes());runtime.chmod(0o600);os.chown(runtime,user.pw_uid,user.pw_gid)
 # Native CLI may generate its own runtime-only internal/JWT secrets.
 INI=str(runtime)
 cli('migrate')
 source=sql("SELECT id FROM login_source WHERE name='Kanidm';")
 if not source:
  # Native CLI validates the source. Secret is injected separately over stdin.
  cli('admin','auth','add-oauth','--name','Kanidm','--provider','openidConnect','--key','mrjam-forgejo','--auto-discover-url',DISCOVERY,'--scopes','openid','--scopes','profile','--scopes','email','--skip-local-2fa')
  source=sql("SELECT id FROM login_source WHERE name='Kanidm';")
 if not source.isdigit():raise RuntimeError('OIDC source missing')
 cfg=json.loads(sql('SELECT cfg FROM login_source WHERE id='+source+';'))
 if cfg.get('Provider')!='openidConnect':raise RuntimeError('Conflicting login source')
 cfg.update(ClientSecret=data['clientSecret'],ClientID='mrjam-forgejo',OpenIDConnectAutoDiscoveryURL=DISCOVERY,SkipLocalTwoFA=True,AllowUsernameChange=False)
 # Do not disable another provider silently if one was added concurrently.
 if sql("SELECT count(*) FROM login_source WHERE is_active AND id<>"+source+';')!='0':raise RuntimeError('Unexpected second login provider')
 accounts=json.loads(sql('SELECT coalesce(json_agg(json_build_object(\'id\',id,\'name\',name,\'admin\',is_admin)),\'[]\') FROM "user" WHERE lower_name IN (\'mrjam-admin\',\'mrjam\');'))
 if not accounts:
  cli('admin','user','create','--username','MrJam','--email','forgejo-admin@mrj.am','--admin','--random-password','--random-password-length','40','--must-change-password=false')
  accounts=json.loads(sql('SELECT json_agg(json_build_object(\'id\',id,\'name\',name,\'admin\',is_admin)) FROM "user" WHERE lower_name=\'mrjam\';'))
 if len(accounts)!=1 or not accounts[0]['admin']:raise RuntimeError('Ambiguous existing administrator')
 account=accounts[0]
 # Bind by the existing owner's immutable UUID, never by an email match.
 sql('BEGIN; UPDATE login_source SET cfg='+literal(json.dumps(cfg))+',is_active=true WHERE id='+source+'; UPDATE "user" SET login_type=6,login_source='+source+',login_name='+literal(data['ownerSubject'])+',must_change_password=false WHERE id='+str(account['id'])+'; COMMIT;')
 sql("UPDATE \"user\" SET prohibit_login=true WHERE lower_name='forgejo-validation' AND login_type IN (0,1) AND NOT is_admin;")
 (STATE/'binding.json').write_text(json.dumps({'sourceId':int(source),'administratorId':account['id'],'name':account['name']}))

def api(path,token,data=None):
 req=urllib.request.Request('http://127.0.0.1:3004/api/v1/'+path,headers={'Authorization':'token '+token,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
 with urllib.request.urlopen(req,timeout=20) as r:return json.load(r) if r.status!=204 else None

def account():
 global INI
 INI='/var/lib/forgejo/custom/conf/app.ini'
 binding=json.loads((STATE/'binding.json').read_text());name=binding['name']
 if name=='MrJam':
  P('/var/lib/forgejo-bootstrap/initial-admin.txt').unlink(missing_ok=True)
  return
 if name!='mrjam-admin':raise RuntimeError('Unexpected administrator name')
 label='declarative-rename-'+uuid.uuid4().hex
 output=cli('admin','user','generate-access-token','--username',name,'--token-name',label,'--scopes','write:admin,write:user','--raw')
 token=output.splitlines()[-1]
 try:
  for attempt in range(30):
   try:api('user',token);break
   except Exception:
    if attempt==29:raise
    time.sleep(.5)
  api('admin/users/'+name+'/rename',token,{'new_username':'MrJam'})
  check=api('user',token)
  if check['id']!=binding['administratorId'] or check['login']!='MrJam' or not check['is_admin']:raise RuntimeError('Rename changed administrator identity')
  binding['name']='MrJam';(STATE/'binding.json').write_text(json.dumps(binding))
 finally:
  sql('DELETE FROM access_token WHERE uid='+str(binding['administratorId'])+' AND name='+literal(label)+';')
 # This bootstrap password is no longer an available authentication method.
 P('/var/lib/forgejo-bootstrap/initial-admin.txt').unlink(missing_ok=True)

if __name__=='__main__':
 os.umask(0o077)
 phase,STATE,PG,FORGEJO,INI,KANIDM,CURL,LIB=sys.argv[1:];STATE=P(STATE)
 DISCOVERY='https://log.mrj.am/oauth2/openid/mrjam-forgejo/.well-known/openid-configuration'
 assert os.geteuid()==0 and phase in ('prepare','account')
 {'prepare':prepare,'account':account}[phase]()
