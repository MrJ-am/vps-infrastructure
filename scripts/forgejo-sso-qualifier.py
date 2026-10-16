#!/usr/bin/env python3
"""Manual native integration: real Kanidm MFA/code/PKCE and real Forgejo.

Loopback only, disposable accounts and databases. The browser's IdP UI step is
mediated through the native authorise API using a genuinely MFA-issued session;
no ID token, code exchange, signature verification or Forgejo login is mocked.
"""
import argparse,base64,configparser,hashlib,json,os,pathlib,re,secrets,shutil,ssl,subprocess,sys,tempfile,time,urllib.error,urllib.parse,urllib.request
from playwright.sync_api import sync_playwright
P=pathlib.Path;ROOT=P(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from kanidm_reel import KanidmLocal
from kanidm_politiques import creer_neuf_mfa

class Native(KanidmLocal):
 def __init__(self,package,curl):
  # Explicit dynamic-loader adapters are needed outside the portable /nix root.
  self.paquet=P(package);self.curl=P(curl);self.processus=None;self.rounds=5000
 def commande(self,*args):
  if args[0]=='cert-generate':
   s=self.config.read_text().replace('domain = "log.mrj.am"','domain = "localhost"').replace('origin = "https://log.mrj.am"',f'origin = "https://localhost:{self.port}"')
   self.config.write_text(s+'role = "WriteReplicaNoUI"\n')
  value=super().commande(*args)
  if args[0]=='cert-generate':
   subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(self.root/'key.pem'),'-out',str(self.ca),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,DNS:log.mrj.am'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  return value
 def __exit__(self,error,*args):
  if error and hasattr(self,'log'):
   self.log.flush();dest=OUTPUT.with_suffix('.native-private.log');dest.write_bytes((self.root/'serveur.log').read_bytes());dest.chmod(0o600)
  super().__exit__(False,*args)

def run(args,*,env=None,cwd=None,check=True):
 r=subprocess.run(list(map(str,args)),capture_output=True,text=True,env=env,cwd=cwd,timeout=90)
 if r.returncode and check:
  p=OUTPUT.with_suffix('.command-private.log');p.write_text(r.stderr+'\n'+r.stdout);p.chmod(0o600)
  raise RuntimeError('Native local command failed: '+P(str(args[0])).name)
 return r if not check else r.stdout.strip()

def qualify(a):
 proof={'forgejo':'16.0.3','nativeIdpPackage':a.kanidm_version,'production':False,'idpUiMediatedByNativeApi':True}
 with Native(a.kanidm,a.curl) as n, tempfile.TemporaryDirectory(prefix='forgejo-sso-') as tmp:
  tmp=P(tmp);token=creer_neuf_mfa(n);owner=n.uuid
  op=n.login('idm_admin',n.recuperer('idm_admin'),privilegie=True)
  def mutation(path,data=None,method=None):
   status,v=n.http(path,data,token=op,method=method)
   assert status==200,(path,status)
   return v
  mutation('/v1/oauth2/_basic',{'attrs':{'name':['mrjam-forgejo'],'displayname':['Forgejo'],'oauth2_rs_origin_landing':['https://localhost:3306/'],'oauth2_strict_redirect_uri':['true']}})
  mutation('/v1/oauth2/mrjam-forgejo/_attr/oauth2_rs_origin',['https://localhost:3306/user/oauth2/Kanidm/callback'])
  mutation('/v1/oauth2/mrjam-forgejo/_attr/oauth2_prefer_short_username',['true'])
  mutation('/v1/oauth2/mrjam-forgejo/_scopemap/idm_all_persons',['openid','profile','email'])
  clientSecret=mutation('/v1/oauth2/mrjam-forgejo/_basic_secret')
  assert any(v['attrs'].get('name')==['mrjam-forgejo'] for v in mutation('/v1/oauth2'))
  mutation('/v1/group',{'attrs':{'name':['mrjam-proprietaire-policy']}})
  mutation('/v1/group/mrjam-proprietaire-policy/_attr/member',[owner])
  member=mutation('/v1/group/mrjam-proprietaire-policy')['attrs']['member'][0].split('@',1)[0]
  assert mutation('/v1/person/'+member)['attrs']['uuid']==[owner]
  proof['nativeOwnerGroupLookup']=True
  # Exercise recovery of the technical account after it has been disabled.
  n.commande('disable-account','idm_admin')
  n.login('idm_admin',n.recuperer('idm_admin'),privilegie=True)
  proof['technicalAdminRecoveryAfterDisable']=True
  cfg=configparser.ConfigParser(interpolation=None);cfg.optionxform=str
  cfg['DEFAULT']={'RUN_USER':os.environ.get('USER','agent'),'RUN_MODE':'prod','WORK_PATH':str(tmp),'APP_NAME':'Forgejo SSO isolation'}
  cfg['server']={'PROTOCOL':'https','DOMAIN':'localhost','ROOT_URL':'https://localhost:3306/','HTTP_ADDR':'127.0.0.1','HTTP_PORT':'3306','CERT_FILE':str(n.ca),'KEY_FILE':str(n.root/'key.pem'),'STATIC_ROOT_PATH':a.static_root,'DISABLE_SSH':'true','OFFLINE_MODE':'true'}
  cfg['database']={'DB_TYPE':'sqlite3','PATH':str(tmp/'forgejo.db')}
  cfg['security']={'INSTALL_LOCK':'true','SECRET_KEY':secrets.token_hex(32)}
  cfg['service']={'DISABLE_REGISTRATION':'true','ALLOW_ONLY_EXTERNAL_REGISTRATION':'true','REQUIRE_SIGNIN_VIEW':'true','ENABLE_INTERNAL_SIGNIN':'false','ENABLE_BASIC_AUTHENTICATION':'false','DEFAULT_ALLOW_CREATE_ORGANIZATION':'false'}
  cfg['oauth2_client']={'ENABLE_AUTO_REGISTRATION':'true','ACCOUNT_LINKING':'disabled','USERNAME':'nickname','OPENID_CONNECT_SCOPES':'openid profile email'}
  cfg['openid']={'ENABLE_OPENID_SIGNIN':'false','ENABLE_OPENID_SIGNUP':'false'}
  cfg['repository']={'MAX_CREATION_LIMIT':'1','FORCE_PRIVATE':'true'}
  cfg['quota']={'ENABLED':'true'};cfg['quota.default']={'TOTAL':'1 KiB'}
  cfg['actions']={'ENABLED':'false'};cfg['mailer']={'ENABLED':'false'};cfg['log']={'MODE':'console','LEVEL':'Warn'}
  ini=tmp/'app.ini'
  with ini.open('w') as file:cfg.write(file)
  env=os.environ.copy();env.update(FORGEJO_WORK_DIR=str(tmp),FORGEJO_CUSTOM=str(tmp/'custom'),SSL_CERT_FILE=str(n.ca))
  def cli(*args):return run([a.forgejo,'--config',ini,*args],env=env)
  cli('migrate')
  cli('admin','auth','add-oauth','--name','Kanidm','--provider','openidConnect','--key','mrjam-forgejo','--auto-discover-url',f'https://localhost:{n.port}/oauth2/openid/mrjam-forgejo/.well-known/openid-configuration','--scopes','openid','--scopes','profile','--scopes','email','--skip-local-2fa')
  import sqlite3
  db=sqlite3.connect(tmp/'forgejo.db');sid,raw=db.execute('SELECT id,cfg FROM login_source').fetchone();source=json.loads(raw);source['ClientSecret']=clientSecret;db.execute('UPDATE login_source SET cfg=? WHERE id=?',(json.dumps(source),sid));db.commit();db.close()
  cli('admin','user','create','--username','MrJam','--email','admin@example.test','--admin','--random-password','--must-change-password=false')
  db=sqlite3.connect(tmp/'forgejo.db');db.execute('UPDATE user SET login_type=6,login_source=?,login_name=? WHERE lower_name=?',(sid,owner,'mrjam'));db.commit();db.close()
  bad=cli('admin','user','create','--username','local-only','--email','local@example.test','--random-password','--must-change-password=false')
  password=re.search("generated random password is '(.*?)'",bad).group(1)
  logs=(tmp/'server.log').open('w');proc=subprocess.Popen([a.forgejo,'--config',str(ini),'web'],env=env,stdout=logs,stderr=logs)
  tls=ssl.create_default_context(cafile=str(n.ca));base='https://localhost:3306'
  def api(path,credential,data=None,method=None):
   req=urllib.request.Request(base+'/api/v1/'+path,headers={'Authorization':'token '+credential,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None,method=method)
   try:
    with urllib.request.urlopen(req,context=tls,timeout=15) as r:return r.status,json.load(r) if r.status!=204 else None
   except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
  try:
   for attempt in range(100):
    try:urllib.request.urlopen(base+'/user/login',context=tls,timeout=1);break
    except Exception:time.sleep(.2)
   else:raise RuntimeError('Local Forgejo did not start')
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    def login(uat):
     context=browser.new_context(ignore_https_errors=True)
     page=context.new_page();page.goto(base+'/user/login');assert page.locator('input[name=password]').count()==0
     page.locator('a[href*="/user/oauth2/Kanidm"]').click();page.wait_for_load_state('load')
     url=urllib.parse.urlsplit(page.url);q=urllib.parse.parse_qs(url.query)
     assert url.netloc==f'localhost:{n.port}' and url.path=='/ui/oauth2'
     assert q.get('code_challenge_method')==['S256'] and len(q.get('state',[''])[0])>10
     status,v,hs=n.http('/oauth2/authorise?'+url.query,token=uat,headers=True)
     if status==200 and isinstance(v,dict) and 'ConsentRequested' in v:
      status,v,hs=n.http('/oauth2/authorise/permit',v['ConsentRequested']['consent_token'],token=uat,headers=True)
     assert status in (200,302) and 'location' in hs,('nativeAuthorisation',status)
     page.goto(hs['location']);page.wait_for_load_state('load')
     page.goto(base+'/user/settings');assert '/user/login' not in page.url
     return context,page
    context,page=login(token)
    assert 'MrJam' in page.content(),'Existing administrator binding failed'
    proof['existingAdminBoundByUuid']=True;context.close()
    n.nom='fixture-second';n.mail='second@example.test';n.password='Fixture-second-'+secrets.token_urlsafe(32)
    uat=creer_neuf_mfa(n);context,page=login(uat)
    proof['nativeMfaOidcPkceEs256']=True
    db=sqlite3.connect(tmp/'forgejo.db');username,is_admin=db.execute('SELECT name,is_admin FROM user WHERE login_type=6 AND login_name=?',(n.uuid,)).fetchone();db.close()
    assert username!='MrJam' and not is_admin
    assert username in page.content()
    proof['externalOnlyAutomaticAccount']=True
    negative=browser.new_context(ignore_https_errors=True);anon=negative.new_page();anon.goto(base+'/user/login')
    csrf=anon.evaluate('window.config.csrfToken')
    status=anon.request.post(base+'/user/login',form={'user_name':'local-only','password':password,'_csrf':csrf}).status
    assert status==403,status
    basic=base64.b64encode(('local-only:'+password).encode()).decode();assert anon.request.get(base+'/api/v1/user',headers={'Authorization':'Basic '+basic}).status in (401,403)
    negative.close()
    proof['localPasswordAndBasicRejected']=True
    pat=cli('admin','user','generate-access-token','--username',username,'--token-name','fixture-user','--scopes','write:repository,write:user','--raw').splitlines()[-1]
    admin=cli('admin','user','generate-access-token','--username','MrJam','--token-name','fixture-admin','--scopes','all','--raw').splitlines()[-1]
    assert api('user',pat)[0]==200
    first=api('user/repos',pat,{'name':'one','private':True});assert first[0]==201,first
    second=api('user/repos',pat,{'name':'two','private':True});assert second[0] in (403,409,422,500),second
    assert len(api('user/repos',pat)[1])==1
    if second[0]==500:
     logs.flush();assert 'user has reached maximum limit of repositories' in (tmp/'server.log').read_text()
    proof['repositoryCountRefusalHttpStatus']=second[0]
    proof['repositoryCountEnforced']=True
    assert api('admin/users/'+username,admin,{'max_repo_creation':2},'PATCH')[0]==200
    assert api('user/repos',pat,{'name':'two','private':True})[0]==201
    proof['perUserCountOverride']=True
    initial=api('repos/'+username+'/one/contents/first.bin',pat,{'content':base64.b64encode(secrets.token_bytes(2048)).decode(),'message':'quota fixture'})
    assert initial[0]==201,initial
    for attempt in range(40):
     usage=api('admin/users/'+username+'/quota',admin)[1]['used']['size']['repos']['private']
     if usage>1024:break
     time.sleep(.25)
    assert usage>1024,'Repository accounting did not update'
    proof['oneWriteCanExceedStorageThreshold']=True
    content={'content':base64.b64encode(b'quota test').decode(),'message':'quota fixture'}
    status,_=api('repos/'+username+'/one/contents/test.txt',pat,content)
    assert status in (403,413),status
    proof['defaultStorageQuotaEnforced']=True
    rules={'name':'fixture-storage','rules':[{'name':'fixture-storage-rule','limit':0,'subjects':['size:all']}]}
    assert api('admin/quota/groups',admin,rules)[0]==201
    assert api('admin/users/'+username+'/quota/groups',admin,{'groups':['fixture-storage']},'POST')[0]==204
    status,_=api('repos/'+username+'/one/contents/test.txt',pat,content)
    assert status in (403,413),status
    proof['storageGroupQuotaEnforced']=True
    assert api('admin/quota/rules/fixture-storage-rule',admin,{'limit':-1},'PATCH')[0]==200
    status,_=api('repos/'+username+'/one/contents/test.txt',pat,content)
    assert status==201,status
    proof['storageGroupCanBeChanged']=True
    context.close();browser.close()
  except BaseException:
   logs.flush();dest=OUTPUT.with_suffix('.forgejo-private.log');dest.write_bytes((tmp/'server.log').read_bytes());dest.chmod(0o600);raise
  finally:
   proc.terminate();proc.wait(timeout=20);logs.close()
 return proof

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--forgejo',required=True);p.add_argument('--static-root',required=True);p.add_argument('--kanidm',required=True);p.add_argument('--kanidm-version',required=True);p.add_argument('--curl',default='/usr/bin/curl');p.add_argument('--output',type=P,required=True)
 a=p.parse_args();OUTPUT=a.output;os.umask(0o077)
 proof=qualify(a);OUTPUT.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
