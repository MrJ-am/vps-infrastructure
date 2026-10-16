#!/usr/bin/env python3
"""Closed production probes. A disposable root-issued PAT tests API/Git only.

This does not claim an interactive owner login: their Kanidm MFA stays personal.
The transport captures the PAT privately and always asks this script to revoke it.
"""
import base64,datetime,json,os,pathlib,re,secrets,subprocess,sys,time,urllib.request,urllib.error
P=pathlib.Path;USER='MrJam';REPO='org-validation'

def run(args,*,input=None,timeout=180):
 r=subprocess.run(list(map(str,args)),input=input,capture_output=True,text=True,timeout=timeout)
 if r.returncode:
  (D/'sso-validation-private.log').write_text(r.stderr+'\n'+r.stdout)
  raise RuntimeError('SSO production probe failed: '+P(str(args[0])).name)
 return r.stdout.strip()

def sql(text):return run(['runuser','-u','postgres','--','psql','-XAtq','--set=ON_ERROR_STOP=1','-d','forgejo'],input=text)

def api(path,data=None,method=None):
 req=urllib.request.Request('http://127.0.0.1:3004/api/v1/'+path,headers={'Authorization':'token '+TOKEN,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None,method=method)
 for attempt in range(40):
  try:
   with urllib.request.urlopen(req,timeout=15) as r:return json.load(r) if r.status!=204 else None
  except urllib.error.HTTPError:raise
  except urllib.error.URLError:
   if attempt==39:raise
   time.sleep(.25)

def clean():
 path=D/'sso-validation-token.json'
 if path.exists():
  record=json.loads(path.read_text());assert re.fullmatch('forgejo-sso-probe-[0-9a-f]{32}',record['name']) and isinstance(record['uid'],int)
  sql("DELETE FROM access_token WHERE uid="+str(record['uid'])+" AND name='"+record['name']+"';")
  path.unlink()

def credential():
 global TOKEN
 clean()
 uid=int(sql('SELECT id FROM "user" WHERE name=\'MrJam\' AND is_admin AND login_type=6;'))
 label='forgejo-sso-probe-'+secrets.token_hex(16)
 expression='(import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[/etc/nixos/configuration.nix];}).config.services.forgejo.package.outPath'
 package=json.loads(run(['nix-instantiate','-I','nixpkgs='+NIXPKGS,'--eval','--strict','--json','--expr',expression]))
 output=run(['runuser','-u','forgejo','--','env','FORGEJO_WORK_DIR=/var/lib/forgejo','FORGEJO_CUSTOM=/var/lib/forgejo/custom',package+'/bin/forgejo','admin','user','generate-access-token','--username',USER,'--token-name',label,'--scopes','all','--raw'])
 TOKEN=output.splitlines()[-1];assert re.fullmatch('[0-9a-f]{40}',TOKEN)
 (D/'sso-validation-token.json').write_text(json.dumps({'uid':uid,'name':label}))
 return uid

def state():
 account=api('user');assert account['login']==USER and account['is_admin']
 source=json.loads(sql("SELECT cfg FROM login_source WHERE name='Kanidm' AND is_active AND type=6;"))
 assert source['ClientID']=='mrjam-forgejo' and source['OpenIDConnectAutoDiscoveryURL']=='https://log.mrj.am/oauth2/openid/mrjam-forgejo/.well-known/openid-configuration'
 assert source['ClientSecret'] and source['SkipLocalTwoFA'] and not source['AllowUsernameChange']
 assert sql('SELECT count(*) FROM login_source WHERE is_active;')=='1'
 repo=api('repos/'+USER+'/'+REPO);assert repo['private']
 head=api('repos/'+USER+'/'+REPO+'/branches/main')['commit']['id']
 return {'identityProvider':'Kanidm','domain':'forge.mrj.am','username':USER,'repository':REPO,'private':True,'administratorBoundByNativeUuid':True,'head':head,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def seed():
 try:repo=api('repos/'+USER+'/'+REPO)
 except urllib.error.HTTPError as e:
  if e.code!=404:raise
  repo=api('user/repos',{'name':REPO,'private':True,'default_branch':'main'})
 assert repo['private']
 for file in sorted((D/'payload/fixtures').rglob('*')):
  if not file.is_file():continue
  route='repos/'+USER+'/'+REPO+'/contents/'+str(file.relative_to(D/'payload/fixtures'))
  try:current=api(route)
  except urllib.error.HTTPError as e:
   if e.code!=404:raise
   current=None
  if current and base64.b64decode(current['content'])==file.read_bytes():continue
  data={'content':base64.b64encode(file.read_bytes()).decode(),'message':'Validation privée Org et connexion Kanidm'}
  if current:data['sha']=current['sha']
  api(route,data,'PUT' if current else 'POST')
 # Exercise the actual quota administration API with a rule assigned to nobody.
 label='probe-quota-'+secrets.token_hex(5);rule=label+'-storage'
 api('admin/quota/groups',{'name':label,'rules':[{'name':rule,'limit':1024,'subjects':['size:all']}]})
 groups=api('admin/quota/groups');assert any(g['name']==label for g in groups)
 api('admin/quota/groups/'+label,method='DELETE');api('admin/quota/rules/'+rule,method='DELETE')
 value=state();value['quotaAdministrationApi']=True
 keys=run(['ssh-keyscan','-p','2222','127.0.0.1'])
 value['knownHosts']='\n'.join(l.replace('[127.0.0.1]:2222','[forge.mrj.am]:2222') for l in keys.splitlines() if not l.startswith('#'))+'\n'
 value['password']=TOKEN  # Captured privately by the existing SSH operator.
 print(json.dumps(value))

def persist():
 before=state();protected=('sshd','nginx','postgresql','mrjam-metier','kanidm','phpfpm-nextcloud','vision-embeddings')
 pids={n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in protected}
 old=run(['systemctl','show','forgejo','-p','MainPID','--value']);run(['systemctl','restart','forgejo'])
 assert old!=run(['systemctl','show','forgejo','-p','MainPID','--value'])
 assert state()['head']==before['head']
 assert pids=={n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in protected}
 run(['systemctl','start','forgejo-backup-qualification'],timeout=300)
 receipt=json.loads(P('/var/backup/forgejo/qualification.json').read_text());assert receipt['semanticFingerprintsEqual'] and receipt['repositoriesFsck']>=1
 assert state()['head']==before['head']
 print(json.dumps({'identityProvider':'Kanidm','persistenceAfterForgejoRestart':True,'head':before['head'],'protectedPidsUnchanged':True,'backup':receipt,'fullVpsReboot':False}))

if __name__=='__main__':
 os.umask(0o077);phase,revision=sys.argv[1:];assert os.geteuid()==0 and re.fullmatch('[0-9a-f]{40}',revision)
 D=P('/root/mrjam-corrections/forgejo')/revision
 NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
 assert phase in ('seed','clean','persistance')
 if phase=='clean':clean()
 else:
  prepared=json.loads((D/'prepared.json').read_text());assert str(P('/run/current-system').resolve())==prepared['generation']
  credential()
  try:{'seed':seed,'persistance':persist}[phase]()
  except BaseException:clean();raise
  finally:
   if phase=='persistance':clean()
