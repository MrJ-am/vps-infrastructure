#!/usr/bin/env python3
"""Production checks restricted to the explicitly requested private Org test repo.

The parent SSH operator captures stdout privately and encrypts the test credential
before publishing any result. The administrator credential is never read.
"""
import base64,datetime,hashlib,json,os,pathlib,re,subprocess,sys,time,urllib.request,urllib.error
P=pathlib.Path
USER='forgejo-validation';REPO='org-validation';DOMAIN='forge.mrj.am'

def run(args,*,env=None,input=None):
 r=subprocess.run([str(a) for a in args],env=env,input=input,capture_output=True,text=True,timeout=180)
 if r.returncode:
  (D/'qualification-private.log').write_text(r.stderr+'\n'+r.stdout)
  raise RuntimeError('Production qualification failed: '+P(str(args[0])).name)
 return r.stdout.strip()

def api(path,data=None,method=None):
 auth=base64.b64encode((USER+':'+C['password']).encode()).decode()
 req=urllib.request.Request('http://127.0.0.1:3004/api/v1/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Basic '+auth,'Content-Type':'application/json'},method=method)
 for attempt in range(20):
  try:
   with urllib.request.urlopen(req,timeout=30) as r:return json.load(r) if r.status!=204 else None
  except urllib.error.HTTPError:raise
  except urllib.error.URLError:
   if attempt==19:raise
   time.sleep(.5)

def meta():
 repo=api('repos/'+USER+'/'+REPO);assert repo['private']
 head=api('repos/'+USER+'/'+REPO+'/branches/main')['commit']['id']
 roles=json.loads(run(['runuser','-u','postgres','--','psql','-XAtq','-d','postgres','-c',"SELECT json_build_object('superuser',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'replication',rolreplication,'bypassrls',rolbypassrls) FROM pg_roles WHERE rolname='forgejo';"]))
 assert roles and not any(roles.values())
 keyscan=run(['ssh-keyscan','-p','2222','127.0.0.1'])
 known='\n'.join(line.replace('[127.0.0.1]:2222','['+DOMAIN+']:2222') for line in keyscan.splitlines() if not line.startswith('#'))+'\n'
 return {'domain':DOMAIN,'username':USER,'repository':REPO,'private':True,'head':head,'postgresRole':roles,'knownHosts':known,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def seed():
 global C
 secret=D/'validation-secret.json'
 if not secret.exists():
  env=os.environ.copy();env.update(FORGEJO_WORK_DIR='/var/lib/forgejo',FORGEJO_CUSTOM='/var/lib/forgejo/custom')
  output=run(['runuser','-u','forgejo','--','env','FORGEJO_WORK_DIR=/var/lib/forgejo','FORGEJO_CUSTOM=/var/lib/forgejo/custom',FORGEJO,'admin','user','create','--username',USER,'--email','forgejo-validation@mrj.am','--random-password','--random-password-length','40','--must-change-password=false'])
  password=re.search("generated random password is '(.*?)'",output).group(1)
  secret.write_text(json.dumps({'username':USER,'password':password}));secret.chmod(0o600)
 C=json.loads(secret.read_text())
 me=api('user');assert me['login']==USER and not me['is_admin']
 assert api('version')['version'].startswith('16.0.3')
 import urllib.error
 try:repo=api('repos/'+USER+'/'+REPO)
 except urllib.error.HTTPError as e:
  if e.code!=404:raise
  repo=api('user/repos',{'name':REPO,'private':True,'default_branch':'main'})
 assert repo['private']
 for file in sorted((D/'payload/fixtures').rglob('*')):
  if not file.is_file():continue
  relative=str(file.relative_to(D/'payload/fixtures'));route='repos/'+USER+'/'+REPO+'/contents/'+relative
  try:current=api(route)
  except urllib.error.HTTPError as e:
   if e.code!=404:raise
   current=None
  content=base64.b64encode(file.read_bytes()).decode()
  if current and base64.b64decode(current['content'])==file.read_bytes():continue
  payload={'content':content,'message':'Validation privée Org, Pandoc et MathJax'}
  if current:payload['sha']=current['sha']
  api(route,payload,'PUT' if current else 'POST')
 info=meta();info['password']=C['password']
 print(json.dumps(info))

def persistence():
 before=meta()
 protected={n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in ('sshd','nginx','postgresql','mrjam-metier','kanidm','phpfpm-nextcloud','vision-embeddings')}
 old=run(['systemctl','show','forgejo','-p','MainPID','--value'])
 run(['systemctl','restart','forgejo'])
 after=meta()
 assert old!=run(['systemctl','show','forgejo','-p','MainPID','--value'])
 assert after['head']==before['head'] and after['private']
 assert protected=={n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in protected}
 # The declared qualification service uses the same snapshot/encryption script
 # as the daily timer, then actually restores in a separate PostgreSQL instance.
 run(['systemctl','start','forgejo-backup-qualification'])
 assert run(['systemctl','show','forgejo-backup-qualification','-p','Result','--value'])=='success'
 receipt=json.loads(P('/var/backup/forgejo/qualification.json').read_text())
 assert receipt['isolatedPostgresqlRestore'] and receipt['semanticFingerprintsEqual'] and receipt['repositoriesFsck']>0
 again=meta();assert again['head']==before['head']
 print(json.dumps({'persistenceAfterForgejoRestart':True,'head':again['head'],'protectedPidsUnchanged':True,'backup':receipt,'fullVpsReboot':False}))

if __name__=='__main__':
 os.umask(0o077);phase,revision=sys.argv[1:];assert os.geteuid()==0 and re.fullmatch('[0-9a-f]{40}',revision)
 D=P('/root/mrjam-corrections/forgejo')/revision
 prepared=json.loads((D/'prepared.json').read_text());assert str(P('/run/current-system').resolve())==prepared['generation']
 expression='(import <nixpkgs/nixos/lib/eval-config.nix> { system="x86_64-linux";modules=[/etc/nixos/configuration.nix]; }).config.services.forgejo.package.outPath'
 FORGEJO=json.loads(run(['nix-instantiate','-I','nixpkgs=/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos','--eval','--strict','--json','--expr',expression]))+'/bin/forgejo'
 assert phase in ('seed','persistance')
 C=json.loads((D/'validation-secret.json').read_text()) if (D/'validation-secret.json').exists() else None
 {'seed':seed,'persistance':persistence}[phase]()
