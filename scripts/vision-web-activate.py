#!/usr/bin/env python3
"""Première activation du navigateur et des sessions, avec retour autonome."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

spec=importlib.util.spec_from_file_location('vision_previous',Path(__file__).with_name('vision-activate.py'))
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
previous.EXPECTED_VERSION='1.3.0'
run,require,save=previous.run,previous.require,previous.save


def paths(commit):
    require(re.fullmatch('[0-9a-f]{40}',commit) is not None,'Commit invalide')
    state=Path('/root/vision-web-deployments')/commit
    return state,json.loads((state/'prepared.json').read_text())


def atomic(path,data,mode=0o644):
    path=Path(path);temporary=path.with_name(path.name+'.vision-web-new')
    temporary.write_bytes(data);os.chmod(temporary,mode)
    if path.exists():shutil.copystat(path,temporary)
    # Les identifiants doivent garder le groupe lisible par Nginx.
    if path.exists():
        stat=path.stat();os.chown(temporary,stat.st_uid,stat.st_gid)
    os.replace(temporary,path)


def web_request(origin,path,data=None,cookie=None,csrf=None,extra=None):
    headers={'Origin':origin,'Accept':'application/json'}
    if data is not None:headers['Content-Type']='application/json'
    if cookie:headers['Cookie']=cookie
    if csrf:headers['X-CSRF-Token']=csrf
    headers.update(extra or {})
    request=urllib.request.Request(origin+path,None if data is None else json.dumps(data).encode(),headers)
    for attempt in range(6):
        try:response=urllib.request.urlopen(request,timeout=10)
        except urllib.error.HTTPError as error:response=error
        with response:
            status,head,body=response.status,response.headers,response.read(2*1024*1024)
        if status!=429 or attempt==5:return status,head,json.loads(body) if body else None
        time.sleep(1)


def verify_web(domain,username,password):
    origin='https://'+domain
    query={'query':'__vision_web_activation_probe__','tags':[],'tagMode':'all','state':'all','sort':'title','direction':'asc','limit':1,'offset':0}
    require(web_request(origin,'/api/web/list',query)[0]==401,'Lecture anonyme autorisée')
    status,headers,login=web_request(origin,'/auth/login',{'username':username,'password':password})
    require(status==200,'Connexion web refusée')
    cookie=headers.get('Set-Cookie','')
    require(all(flag in cookie for flag in ('Domain=mrj.am','Secure','HttpOnly','SameSite=Lax')),'Cookie incomplet')
    cookie=cookie.split(';',1)[0];csrf=login['csrf']
    require(web_request(origin,'/api/web/list',query,cookie)[0]==403,'Écriture POST sans CSRF autorisée')
    require(web_request(origin,'/api/web/list',query,cookie,csrf,{'Origin':'https://evil.mrj.am'})[0]==403,'Origine étrangère autorisée')
    status,_,listing=web_request(origin,'/api/web/list',query,cookie,csrf)
    require(status==200 and isinstance(listing.get('sheets'),list),'Lecture web PostgreSQL invalide')
    require(web_request(origin,'/auth/logout',{},cookie,csrf)[0]==200,'Déconnexion impossible')
    require(web_request(origin,'/auth/session',cookie=cookie)[0]==401,'Session encore valide après déconnexion')


def probe_credential():
    openssl=shutil.which('openssl')
    require(openssl is not None,'OpenSSL absent : aucune activation effectuée')
    username='vision-browser-check-'+secrets.token_hex(8)
    password=secrets.token_urlsafe(40)
    encoded=subprocess.run([openssl,'passwd','-6','-stdin'],input=password+'\n',text=True,capture_output=True,check=True).stdout.strip()
    require(encoded.startswith('$6$'),'Empreinte de sonde inattendue')
    return username,password,encoded


def verify_backup_timers():
    for database in ('matheval','vision'):
        require(run('systemctl','is-active','postgresqlBackup-'+database+'.timer').strip()=='active',
                'Sauvegarde PostgreSQL inactive : '+database)


def rollback(commit,stop_apply=True):
    state,report=paths(commit)
    if stop_apply:
        subprocess.run(['systemctl','stop','vision-web-apply-'+commit[:12]],check=False)
    with (state/'finalize.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (state/'committed.json').exists():return
        (state/'rollback-started').touch()
        atomic('/var/lib/vision/auth/htpasswd',(state/'credentials.before').read_bytes(),0o640)
        atomic('/etc/nixos/configuration.nix',(state/'configuration.nix.before').read_bytes())
        previous.restore_current_link('/srv/vision/current',report['current_release'])
        run(Path(report['old_system'])/'bin/switch-to-configuration','test',visible=True)
        previous.register_system(report['old_boot'])
        run(Path(report['old_boot'])/'bin/switch-to-configuration','boot',visible=True)
        run('systemctl','restart','vision.service')
        require(all(run('systemctl','is-active',s).strip()=='active' for s in ('sshd','nginx','postgresql','matheval','vision')),'Retour incomplet')
        save(state/'rollback.json',{'commit':commit,'restored':True})


def apply(commit):
    require(os.geteuid()==0,'Exécution root sur le VPS requise')
    os.umask(0o077);state,report=paths(commit)
    require(report['app_version']=='1.3.0' and report['activated'] is False,'Préparation inattendue')
    require(not any((state/p).exists() for p in ('pending.json','committed.json','rollback-started')),'Opération déjà engagée')
    require(str(Path('/run/current-system').resolve())==report['old_system'],'Génération active modifiée')
    require(str(Path('/nix/var/nix/profiles/system').resolve())==report['old_boot'],'Génération de démarrage modifiée')
    require(previous.sha256('/etc/nixos/configuration.nix')==report['configuration_sha256'],'Configuration modifiée')
    require(previous.sha256('/var/lib/vision/auth/htpasswd')==report['credentials_sha256'],'Identifiants modifiés')
    require(str(Path('/srv/vision/current').resolve())==report['current_release'],'Application modifiée')
    require('187.77.95.158' in {x[4][0] for x in socket.getaddrinfo(report['domain'],443,socket.AF_INET)},'DNS inattendu')
    # Résoudre et vérifier les outils avant toute modification du serveur.
    username,password,encoded=probe_credential()
    locks=[]
    for path in ('/srv/matheval/deploy.lock','/srv/vision/deploy.lock'):
        lock=open(path,'a');fcntl.flock(lock,fcntl.LOCK_EX);locks.append(lock)
    # Le retour est exécuté par systemd même si le runner ou SSH disparaît.
    save(state/'pending.json',{'commit':commit,'started':int(time.time())})
    timer='vision-web-rollback-'+commit[:12]
    run('systemd-run','--unit='+timer,'--on-active=15m','--timer-property=AccuracySec=1s',
        '--setenv=PATH='+os.environ['PATH'],sys.executable,Path(__file__).resolve(),'rollback',commit)
    require(run('systemctl','is-active',timer+'.timer').strip()=='active','Retour autonome non armé')
    candidate=Path(report['candidate']);credentials=Path('/var/lib/vision/auth/htpasswd')
    try:
        previous.detach_current_link('/srv/vision/current')
        run(candidate/'bin/switch-to-configuration','test',visible=True)
        require(all(run('systemctl','is-active',s).strip()=='active' for s in ('sshd','nginx','postgresql','matheval','vision','mrj-auth')),'Un service requis est inactif')
        # Identifiant de sonde éphémère, ajouté sans remplacer le compte humain.
        atomic(credentials,(state/'credentials.before').read_bytes().rstrip(b'\n')+f'\n{username}:{encoded}\n'.encode(),0o640)
        previous.wait_for(lambda:previous.verify_http(report['domain'],username,password),'API existante invalide',attempts=5)
        verify_web(report['domain'],username,password)
        atomic(credentials,(state/'credentials.before').read_bytes(),0o640)
        password='';encoded=''
        require(previous.sha256(credentials)==report['credentials_sha256'],'Identifiants non restaurés après sondes')
        run('python3',Path(report['installed'])/'scripts/probe.py',visible=True)
        # Les sauvegardes planifiées des deux bases doivent rester actives.
        verify_backup_timers()
        with (state/'finalize.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            require(not (state/'rollback-started').exists(),'Le retour a commencé')
            save(state/'ready.json',{'commit':commit,'candidate':report['candidate'],'browser_verified':True})
        print('VISION WEB TESTÉ ; en attente des contrôles SSH et HTTP indépendants.',flush=True)
    except Exception:
        rollback(commit,stop_apply=False)
        raise
    finally:
        for lock in locks:lock.close()

def finalize(commit):
    state,report=paths(commit)
    with (state/'finalize.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        require((state/'ready.json').exists() and not (state/'rollback-started').exists(),'Candidat non validé ou retour commencé')
        require(not (state/'committed.json').exists(),'Candidat déjà enregistré')
        require(str(Path('/run/current-system').resolve())==report['candidate'],'Le candidat ne tourne plus')
        require(previous.sha256('/etc/nixos/configuration.nix')==report['configuration_sha256'],'Configuration modifiée')
        require(previous.sha256('/var/lib/vision/auth/htpasswd')==report['credentials_sha256'],'Identifiants modifiés')
        require(all(run('systemctl','is-active',s).strip()=='active' for s in ('sshd','nginx','postgresql','matheval','vision','mrj-auth')),'Un service est inactif')
        pointer=f"{{ imports = [ {report['installed']}/hosts/hostinger/configuration.nix ]; }}\n"
        atomic('/etc/nixos/configuration.nix',pointer.encode())
        previous.register_system(report['candidate'])
        run(Path(report['candidate'])/'bin/switch-to-configuration','boot',visible=True)
        require(str(Path('/nix/var/nix/profiles/system').resolve())==report['candidate'],'Enregistrement incomplet')
        save(state/'committed.json',{**report,'activated':True,'browser_verified':True,'credentials_preserved':True})
    run('systemctl','stop','vision-web-rollback-'+commit[:12]+'.timer')
    print('VISION WEB ACTIVE : '+json.dumps({'commit':commit,'app_commit':report['app_commit'],'candidate':report['candidate'],'durable_credentials':report['durable_credentials']}),flush=True)


if __name__=='__main__':
    try:
        mode,commit=sys.argv[1:]
        if mode=='start':
            paths(commit)
            run('systemd-run','--unit=vision-web-apply-'+commit[:12],'--wait','--collect','--pipe',
                '--setenv=PATH='+os.environ['PATH'],sys.executable,Path(__file__).resolve(),'apply',commit,visible=True)
        elif mode=='apply':apply(commit)
        elif mode=='rollback':rollback(commit)
        elif mode=='finalize':finalize(commit)
        else:raise ValueError('Mode inconnu')
    except Exception as error:
        print('ÉCHEC VISION WEB : '+str(error),file=sys.stderr);sys.exit(1)
