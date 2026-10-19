"""Closed Nextcloud SSO operation through the existing infrastructure runner.
Private state, encrypted backup, isolated restore, leased configuration and timed
code-only return. Never restore an old database over current application writes.
"""
import datetime,hashlib,http.cookiejar,importlib.util,json,os,pathlib,pwd,re,shutil,subprocess,sys,tarfile,tempfile,time,urllib.error,urllib.parse,urllib.request
from client import configure,CLIENT,DISCOVERY
P=pathlib.Path
PROTECTED=['postgresql','kanidm','mrjam-metier','forgejo','sshd','vision-embeddings']

def require(ok,message):
    if not ok:raise RuntimeError(message)

def run(args,*,input=None,timeout=180):
    p=subprocess.run(list(map(str,args)),input=input,capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        (D/'command-private.log').write_text(p.stdout+'\n'+p.stderr)
        raise RuntimeError('Command failed: '+P(str(args[0])).name+'; diagnostic retained privately')
    return p.stdout.strip()

def sql(query,db='nextcloud'):
    return run(['runuser','-u','postgres','--','psql','-XAtq','--set=ON_ERROR_STOP=1','-d',db],input=query)

def occ(*args):
    return run(['runuser','-u','nextcloud','--','env','-i','PATH=/run/current-system/sw/bin','USER=nextcloud','HOME=/var/lib/nextcloud','nextcloud-occ',*args])

def evaluate(path, omit_contacts=False):
    expr='''let e=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[PATH];}; c=e.config; in {
      generation=toString c.system.build.toplevel;
      errors=map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      units=builtins.mapAttrs (_: u: u.text) c.systemd.units;
      hosts=builtins.mapAttrs (_: v: {root=toString v.root;locations=builtins.attrNames v.locations;extra=v.extraConfig;}) c.services.nginx.virtualHosts;
      nc={package=toString c.services.nextcloud.package;apps=builtins.mapAttrs (_: a: toString a) c.services.nextcloud.extraApps;};
      settings={oidc=c.services.nextcloud.settings.user_oidc or {};token=c.services.nextcloud.settings.token_auth_enforced or false;hide=c.services.nextcloud.settings.hide_login_form or false;};
      kanidm=toString c.services.kanidm.package;postgres=toString c.services.postgresql.finalPackage;
      age=toString e.pkgs.age;curl=toString e.pkgs.curl;
      recipient=c.services.vision.backupRecipient;
    }'''.replace('PATH',str(path))
    if omit_contacts:
        expr=expr.replace('let e=import', 'let base=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=['+str(path)+'];}; e=import', 1).replace('modules=['+str(path)+'];}; c=e.config;', 'modules=['+str(path)+' ({lib,...}: {services.nextcloud.extraApps=lib.mkForce (builtins.removeAttrs base.config.services.nextcloud.extraApps ["contacts"]);})];}; c=e.config;')
    return json.loads(run(['nix-instantiate','--eval','--strict','--json','--expr',expr],timeout=300))

def pids():return {n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in PROTECTED}
def digest(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def current():return str(P('/run/current-system').resolve())
def metadata():
    return json.loads(sql("SELECT json_agg(json_build_object('uid',u.uid,'admin',EXISTS(SELECT 1 FROM oc_group_user g WHERE g.uid=u.uid AND g.gid='admin'))) FROM oc_users u"))

def invariants(db='nextcloud'):
    # Only hashes leave the SQL connection. All real account and file metadata
    # remain on this server; write activity is paused while comparing.
    out={}
    for table in ['oc_users','oc_group_user','oc_filecache','oc_share','oc_storages','oc_addressbooks','oc_cards','oc_calendars','oc_calendarobjects']:
        out[table]=sql('SELECT count(*)::text || \':\' || coalesce(md5(string_agg(h,\'\' ORDER BY h)),\'empty\') FROM (SELECT md5(row_to_json(t)::text) h FROM '+table+' t) s;',db)
    return out

def lease(state):
    require(current()==state['base'] and digest('/etc/nixos/configuration.nix')==state['entrySha256'],'Production changed since preparation; inspect and prepare again')

def prepare():
    require(not (D/'prepared.json').exists(),'Preparation already exists')
    base=D/'base.nix';base.write_bytes(P('/etc/nixos/configuration.nix').read_bytes())
    require('imports' in base.read_text() and '/root/' in base.read_text(),'Unexpected production entry')
    before=evaluate('/etc/nixos/configuration.nix')
    pending_contacts=False
    if before['generation']!=current():
        # The existing Contacts wrapper was written on Oct 17 but never activated.
        # Reproduce the installed generation exactly; keep its source untouched.
        require('contacts' in before['nc']['apps'],'Unknown difference from installed generation')
        before=evaluate('/etc/nixos/configuration.nix',omit_contacts=True)
        require(before['generation']==current(),'Pending Contacts is not the only difference; inspect again')
        pending_contacts=True
    require(not before['errors'],'Existing Nix assertions failed')
    apps=json.loads(occ('app:list','--output=json'))
    require('user_oidc' not in apps['enabled'] and 'encryption' not in apps['enabled'],'An existing OIDC or encryption configuration requires inspection')
    accounts=metadata()
    # Exact account selection is pinned in target.json after read-only inventory.
    target=json.loads((D/'payload/target.json').read_text())
    uid=target['uid'];require(any(a['uid']==uid and a['admin'] for a in accounts),'Selected existing owner missing')
    require(sorted(a['uid'] for a in accounts)==target['accounts'],'Account inventory changed')
    config=D/'configuration.nix'
    apps_override=''
    if pending_contacts:
        apps_override=' services.nextcloud.extraApps=lib.mkForce ((builtins.removeAttrs staged.services.nextcloud.extraApps ["contacts"]) // {user_oidc=pkgs.nextcloud34Packages.apps.user_oidc;});'
    config.write_text('{lib,pkgs,...}: let staged=(import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[./base.nix];}).config; in { imports = [ ./base.nix ./payload/module.nix ];'+apps_override+' }\n')
    after=evaluate(config);require(not after['errors'],'Candidate Nix assertions failed')
    require(after['nc']['package']==before['nc']['package'],'Nextcloud version changed')
    require({k:v for k,v in after['nc']['apps'].items() if k!='user_oidc'}==before['nc']['apps'],'Existing Nextcloud apps changed')
    require(after['settings']['oidc'].get('auto_provision') is False and after['settings']['token'] and after['settings']['hide'],'SSO settings not effective')
    require(set(before['hosts'])==set(after['hosts']),'Virtual host inventory changed')
    require(all(after['hosts'][n]==v for n,v in before['hosts'].items() if n!='cloud.mrj.am'),'Other virtual host changed')
    require('nextcloud_local_password' in after['hosts']['cloud.mrj.am']['extra'],'Password POST filter missing')
    changes=[n for n in set(before['units'])|set(after['units']) if before['units'].get(n)!=after['units'].get(n)]
    tmpfiles='systemd-tmpfiles-resetup.service'
    if tmpfiles in changes:
        stable=lambda text:'\n'.join(l for l in text.splitlines() if not l.startswith('X-Restart-Triggers='))
        require(stable(before['units'][tmpfiles])==stable(after['units'][tmpfiles]),'Tmpfiles command changed beyond its configuration trigger')
    allowed=lambda n:n.startswith('nextcloud-') or n in ['nginx.service','phpfpm-nextcloud.service',tmpfiles]
    require(all(allowed(n) for n in changes),'Unexpected unit changes: '+','.join(n for n in changes if not allowed(n)))
    for n in ['kanidm','postgres','recipient']:require(before[n]==after[n],'Protected configuration changed: '+n)
    built=run(['nix-build','--no-out-link','--expr','(import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=['+str(config)+'];}).config.system.build.toplevel'],timeout=1800)
    require(built==after['generation'],'Built artifact differs from evaluated candidate')
    for name,path in [('base',before['generation']),('candidate',built),('python',str(P(sys.executable).resolve().parents[1]))]:
        run(['nix-store','--add-root',str(D/(name+'-root')),'--indirect','-r',path])
    for name in ['age','curl']:run(['nix-store','-r',after[name]])
    state={'revision':REV,'base':before['generation'],'generation':built,'entrySha256':digest(base),'preparedAt':time.time(),'uid':uid,'accounts':accounts,'config':after,'protectedPids':pids()}
    (D/'prepared.json').write_text(json.dumps(state))
    print(json.dumps({'phase':'prepared','generation':built,'base':before['generation'],'changedUnits':changes,'pendingContactsPreservedWithoutActivation':pending_contacts,'activated':False}))

def backup(state):
    conf=state['config'];age=P(conf['age'])/'bin/age';keygen=P(conf['age'])/'bin/age-keygen'
    root=P('/var/backup/nextcloud-sso');root.mkdir(mode=0o700,exist_ok=True)
    dest=root/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+REV[:12]);dest.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='nc-sso-backup-',dir=D) as temp:
        temp=P(temp);key=temp/'key';run([keygen,'-o',key]);public=run([keygen,'-y',key])
        run([age,'-r',conf['recipient'],'-o',dest/'key.age',key])
        with (temp/'db.dump').open('wb') as f:
            subprocess.run(['runuser','-u','postgres','--',conf['postgres']+'/bin/pg_dump','--format=custom','--no-owner','--no-acl','nextcloud'],stdout=f,check=True,timeout=300)
        run(['tar','-C','/var/lib/nextcloud','-cpf',temp/'files.tar','config','data'],timeout=300)
        run(['tar','-C',temp,'-cf',temp/'snapshot.tar','db.dump','files.tar'])
        run([age,'-r',public,'-o',dest/'snapshot.tar.age',temp/'snapshot.tar'],timeout=300)
        run([age,'-d','-i',key,'-o',temp/'restored.tar',dest/'snapshot.tar.age'],timeout=300)
        require(digest(temp/'snapshot.tar')==digest(temp/'restored.tar'),'Encrypted backup round trip failed')
        restored=temp/'restored';restored.mkdir();run(['tar','-xf',temp/'restored.tar','-C',restored])
        files=restored/'files';files.mkdir();run(['tar','-xf',restored/'files.tar','-C',files],timeout=300)
        require((files/'config/config.php').is_file() and (files/'data').is_dir(),'Files restore failed')
        db='nextcloud_sso_restore_'+REV[:12]
        require(sql("SELECT count(*) FROM pg_database WHERE datname='"+db+"';",'postgres')=='0','Restore database already exists')
        run(['runuser','-u','postgres','--',conf['postgres']+'/bin/createdb',db])
        try:
            sql('REVOKE ALL ON DATABASE '+db+' FROM PUBLIC;',db)
            with (restored/'db.dump').open('rb') as f:
                subprocess.run(['runuser','-u','postgres','--',conf['postgres']+'/bin/pg_restore','--exit-on-error','--no-owner','--no-acl','-d',db],stdin=f,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300)
            require(invariants(db)==state['invariants'],'Isolated database restore changed invariants')
        finally:run(['runuser','-u','postgres','--',conf['postgres']+'/bin/dropdb',db])
    (D/'backup.json').write_text(json.dumps({'encrypted':True,'restoredInIsolation':True,'path':str(dest)}))

def provision(state):
    conf=state['config'];uid=state['uid']
    spec=importlib.util.spec_from_file_location('native',D/'payload/kanidm-api-privee.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    api=native.KanidmPrive(conf['kanidm'],'/etc/kanidm/server.toml',conf['curl']+'/bin/curl',diagnostic=D/'native-private.log')
    # Cross-check against the independently established Forgejo owner binding.
    subject=json.loads(P('/var/lib/forgejo-identity/client.json').read_text())['ownerSubject']
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        try:
            token=api.login('idm_admin',api.recuperer('idm_admin'),tmp)
            data=configure(api,token,uid,subject)
        finally:api.commande('disable-account','idm_admin')
    stateDir=P('/var/lib/nextcloud-sso');stateDir.mkdir(mode=0o700,exist_ok=True)
    (stateDir/'binding.json').write_text(json.dumps({'ownerSubject':data['ownerSubject'],'nextcloudUid':uid,'client':CLIENT}))
    # Secret only exists in a mode-0600 file readable by the service UID.
    with tempfile.TemporaryDirectory(prefix='nc-sso-secret-',dir='/run') as tmp:
        tmp=P(tmp);u=pwd.getpwnam('nextcloud');os.chown(tmp,u.pw_uid,u.pw_gid)
        secret=tmp/'secret';secret.write_text(data['clientSecret']);secret.chmod(0o600);os.chown(secret,u.pw_uid,u.pw_gid)
        occ('user_oidc:provider','Log','--clientid',CLIENT,'--clientsecret-file',str(secret),'--discoveryuri',DISCOVERY,
          '--mapping-uid','nextcloud_uid','--unique-uid','0','--check-bearer','0','--bearer-provisioning','0','--scope','openid profile email')
    occ('config:app:set','user_oidc','allow_multiple_user_backends','--type','string','--value','0')

def probe():
    class Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),Stop)
    url='https://cloud.mrj.am/login'
    for _ in range(5):
        try:r=opener.open(url,timeout=20)
        except urllib.error.HTTPError as e:r=e
        require(r.code in (301,302,303,307),'Missing SSO redirect')
        url=urllib.parse.urljoin(url,r.headers['Location'])
        if urllib.parse.urlsplit(url).hostname=='log.mrj.am':break
    q=urllib.parse.urlsplit(url);params=urllib.parse.parse_qs(q.query)
    require(q.hostname=='log.mrj.am' and q.path=='/ui/oauth2' and params.get('client_id')==[CLIENT] and params.get('code_challenge_method')==['S256'],'Unexpected OIDC authorization target')
    require(params.get('redirect_uri') in [['https://cloud.mrj.am/index.php/apps/user_oidc/code'],['https://cloud.mrj.am/apps/user_oidc/code']],'Callback mismatch')
    for path in ['/login','/index.php/login?direct=1']:
        try:r=opener.open(urllib.request.Request('https://cloud.mrj.am'+path,data=b'user=&password='),timeout=15)
        except urllib.error.HTTPError as e:r=e
        require(r.code==403,'Password POST still accepted')
    with urllib.request.urlopen('https://cloud.mrj.am/status.php',timeout=15) as r:status=json.load(r)
    require(status['versionstring']=='34.0.4' and not status['maintenance'] and not status['needsDbUpgrade'],'Nextcloud status unhealthy')
    return {'redirectToLog':True,'pkceS256':True,'localPasswordPostDenied':True,'healthy':True}

GATE=P('/run/nextcloud-sso-gate')
GATED=['phpfpm-nextcloud','nextcloud-cron']
def close_gate():
    require(not GATE.exists() or GATE.read_text()==REV,'Another Nextcloud operation owns the gate')
    GATE.write_text(REV);GATE.chmod(0o644)
    for unit in GATED:
        d=P('/run/systemd/system')/(unit+'.service.d');d.mkdir(exist_ok=True)
        p=d/'90-nextcloud-sso.conf';content='[Unit]\nConditionPathExists=!'+str(GATE)+'\n'
        require(not p.exists() or p.read_text()==content,'Concurrent service drop-in')
        p.write_text(content);p.chmod(0o644)
    run(['systemctl','daemon-reload'])
    run(['systemctl','stop','phpfpm-nextcloud.service','nextcloud-cron.timer','nextcloud-cron.service'])

def open_gate():
    require(not GATE.exists() or GATE.read_text()==REV,'Another Nextcloud operation owns the gate')
    for unit in GATED:
        (P('/run/systemd/system')/(unit+'.service.d/90-nextcloud-sso.conf')).unlink(missing_ok=True)
    GATE.unlink(missing_ok=True)
    run(['systemctl','daemon-reload'])
    run(['systemctl','start','phpfpm-nextcloud.service','nextcloud-cron.timer'])

def rollback():
    state=json.loads((D/'prepared.json').read_text())
    entry=P('/etc/nixos/configuration.nix')
    ours='{ ... }: { imports = [ '+str(D/'configuration.nix')+' ]; }\n'
    require(entry.read_text() in [ours,(D/'base.nix').read_text()],'Concurrent configuration prevents automatic return')
    close_gate()
    occ('maintenance:mode','--off')
    # Disable only this newly installed application, preserving every account,
    # file and token, including any writes after the cutover.
    try:occ('app:disable','user_oidc')
    except RuntimeError:pass
    temp=entry.with_name('.nextcloud-sso-return.nix');temp.write_bytes((D/'base.nix').read_bytes());temp.chmod(0o644);temp.replace(entry)
    run(['nix-env','--profile','/nix/var/nix/profiles/system','--set',state['base']])
    run([state['base']+'/bin/switch-to-configuration','switch'],timeout=360)
    occ('maintenance:mode','--off')
    require(current()==state['base'],'Return generation not active')
    open_gate()
    run(['systemctl','stop','nextcloud-sso-return-'+REV[:12]+'.timer'])
    print(json.dumps({'phase':'returned','restoredOldDatabase':False}))

def deploy():
    state=json.loads((D/'prepared.json').read_text());lease(state)
    require(time.time()-state['preparedAt']<86400,'Preparation expired')
    require(metadata()==state['accounts'],'Account inventory changed')
    before=pids();timer='nextcloud-sso-return-'+REV[:12]
    # Qualify independent execution before relying on it for the return path.
    witness=D/'return-witness';witness.unlink(missing_ok=True)
    run(['systemd-run','--unit='+timer+'-witness','--collect','--on-active=1s',sys.executable,str(D/'payload/promote.py'),'witness',REV])
    for _ in range(30):
        if witness.exists():break
        time.sleep(.2)
    require(witness.exists(),'Independent return timer not executed')
    try:
        close_gate()
        occ('maintenance:mode','--on')
        state['invariants']=invariants();(D/'prepared.json').write_text(json.dumps(state))
        backup(state)
        run(['systemctl','start','mrjam-sauvegarde.service'],timeout=300)
        require(run(['systemctl','show','mrjam-sauvegarde','-p','Result','--value'])=='success','Native backup failed')
        lease(state)
        run(['systemd-run','--unit='+timer,'--on-active=10min',sys.executable,str(D/'payload/promote.py'),'retour',REV])
        # NixOS runs occ upgrade; both it and the provider command require
        # maintenance=false. The independent service gate blocks Web and cron.
        occ('maintenance:mode','--off')
        entry=P('/etc/nixos/configuration.nix');temp=entry.with_name('.nextcloud-sso.nix')
        temp.write_text('{ ... }: { imports = [ '+str(D/'configuration.nix')+' ]; }\n');temp.chmod(0o644);temp.replace(entry)
        try:
            run(['nix-env','--profile','/nix/var/nix/profiles/system','--set',state['generation']])
            run([state['generation']+'/bin/switch-to-configuration','switch'],timeout=360)
            provision(state)
            require(invariants()==state['invariants'],'Existing account/file/share/group metadata changed')
            require(pids()==before,'Protected service restarted')
            occ('maintenance:mode','--off')
            open_gate()
            report=probe()
            run(['systemctl','stop',timer+'.timer'])
            report.update(revision=REV,generation=current(),dataPreserved=True,protectedServicesUnchanged=True,personalLoginTested=False)
            (D/'deployed.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
        except BaseException:
            rollback();run(['systemctl','stop',timer+'.timer']);raise
    finally:
        occ('maintenance:mode','--off');open_gate()

if __name__=='__main__':
    os.umask(0o077)
    phase,REV=sys.argv[1:];require(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',REV),'Invalid operation context')
    D=P('/root/mrjam-corrections/nextcloud-sso')/REV
    require(P(__file__).resolve()==D/'payload/promote.py','Unexpected operator path')
    try:
        if phase=='witness':(D/'return-witness').write_text('ok')
        elif phase=='diagnostic':print((D/'deployed.json').read_text() if (D/'deployed.json').exists() else json.dumps({'prepared':(D/'prepared.json').exists()}))
        else:{'preparer':prepare,'deployer':deploy,'retour':rollback}[phase]()
    except Exception as e:
        print(json.dumps({'phase':phase,'stopped':True,'reason':str(e)}));sys.exit(1)
