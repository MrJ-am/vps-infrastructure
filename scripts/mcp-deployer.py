#!/usr/bin/env python3
"""Préparer puis activer le token MCP, exclusivement depuis Actions, avec retour autonome."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time

ENTREE = Path('/etc/nixos/configuration.nix')
SERVICES = ('sshd', 'nginx', 'postgresql', 'matheval', 'vision', 'mrj-auth',
            'postgresqlBackup-matheval.timer', 'postgresqlBackup-vision.timer')


def exiger(condition, message):
    if not condition:raise RuntimeError(message)


def executer(*arguments, visible=False):
    return subprocess.run([str(a) for a in arguments], check=True, text=True,
                          stdout=None if visible else subprocess.PIPE).stdout


def sauver(chemin, valeur):
    temporaire=chemin.with_suffix('.nouveau')
    temporaire.write_text(json.dumps(valeur,ensure_ascii=False,indent=2)+'\n')
    os.replace(temporaire,chemin)


def dossier(revision):
    exiger(re.fullmatch('[0-9a-f]{40}',revision),'Révision exacte requise')
    return Path('/root/mcp-preparations')/revision


def etat():
    return {'actif':str(Path('/run/current-system').resolve()),
            'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
            'configuration':hashlib.sha256(ENTREE.read_bytes()).hexdigest(),
            **{p:str(Path('/srv/'+p+'/current').resolve()) for p in
               ('matheval','vision','vision-interface','logique')}}


def services():
    executer('systemctl','is-active',*SERVICES)


def evaluer(source, configuration, nixpkgs):
    return json.loads(executer('nix-instantiate','--eval','--strict','--json',
        source/'scripts/mcp-config.nix','--argstr','configuration',configuration,
        '-I','nixpkgs='+nixpkgs))


def preparer(revision):
    d=dossier(revision);source=d/'source'
    exiger(not (d/'commence').exists(),'Préparation déjà engagée')
    avant=etat();services()
    exiger(avant['actif']==avant['demarrage'],'Générations désynchronisées')
    exiger(all(Path(avant[n]).is_dir() for n in ('matheval','vision','vision-interface','logique')),
           'Une publication manque : nouvel audit nécessaire')
    (d/'commence').touch()
    nixpkgs=executer('nix-instantiate','--find-file','nixpkgs').strip()
    executer('tar','-cpf',d/'etc-nixos-avant.tar','-C','/etc','nixos')
    shutil.copy2(ENTREE,d/'configuration-avant.nix',follow_symlinks=False)
    installe=Path('/etc/nixos/vps-infrastructure')/('mcp-'+revision)
    shutil.copytree(source,installe)
    reference=evaluer(installe,ENTREE,nixpkgs)
    exiger(reference['systeme']==avant['actif'],'Les sources actives ne reproduisent pas le système')
    configuration=installe/'hosts/hostinger/logique.nix'
    candidat=evaluer(installe,configuration,nixpkgs)
    exiger(candidat['invariant']==reference['invariant'],'Un invariant hors MCP/authentification change')
    racines=Path('/nix/var/nix/gcroots/mcp')/revision;racines.mkdir(parents=True)
    for nom,cible in {'avant':avant['actif'],'nixpkgs':nixpkgs,'python':str(Path(sys.executable).resolve())}.items():
        (racines/nom).symlink_to(cible)
    construit=executer('nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+nixpkgs,
        '-I','nixos-config='+str(configuration),'--out-link',racines/'candidat').strip()
    exiger(construit==candidat['systeme'],'Construction différente de l’évaluation')
    executer(*shlex.split(candidat['nginx']),'-t',visible=True)
    simulation=subprocess.run([construit+'/bin/switch-to-configuration','dry-activate'],check=True,
        text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout
    (d/'simulation.txt').write_text(simulation);print(simulation,flush=True)
    for projet in ('matheval','vision'):
        with (d/(projet+'-avant.dump.age')).open('wb') as sortie:
            subprocess.run([projet+'-backup'],stdout=sortie,check=True)
    # Copie cohérente privée, sans restauration automatique de sessions ou de tokens.
    with sqlite3.connect('file:/var/lib/mrj-auth/sessions.sqlite?mode=ro',uri=True) as original:
        with sqlite3.connect(d/'sessions-avant.sqlite') as sauvegarde:original.backup(sauvegarde)
    executer(sys.executable,source/'scripts/mcp-probe.py','--output',d/'http-avant.json',visible=True)
    temoin=d/'timer-verifie'
    executer('systemd-run','--unit=mcp-temoin-'+revision[:12],'--on-active=2s',
             '--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',temoin)
    for _ in range(15):
        if temoin.exists():break
        time.sleep(1)
    exiger(temoin.exists(),'Timer autonome non vérifié')
    exiger(etat()==avant,'État modifié durant la préparation');services()
    sauver(d/'preparation.json',{'revision':revision,'avant':avant,'nixpkgs':nixpkgs,
        'candidat':construit,'configuration':str(configuration),'python':sys.executable})
    print('Candidat construit, invariants et retour vérifiés ; aucune activation.')


def lire(revision):
    d=dossier(revision)
    return d,json.loads((d/'preparation.json').read_text())


def retour(revision):
    d,r=lire(revision)
    if (d/'enregistre').exists():return
    subprocess.run(['systemctl','stop','mcp-appliquer-'+revision[:12]],check=False)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        if (d/'enregistre').exists():return
        exiger((d/'engage').exists(),'Aucune activation engagée')
        exiger(etat()['actif'] in (r['avant']['actif'],r['candidat']),'Une autre génération est active')
        (d/'retour-engage').touch()
        temporaire=ENTREE.with_suffix('.mcp-retour')
        if temporaire.exists() or temporaire.is_symlink():temporaire.unlink()
        shutil.copy2(d/'configuration-avant.nix',temporaire,follow_symlinks=False)
        os.replace(temporaire,ENTREE)
        executer('nix-env','--profile','/nix/var/nix/profiles/system','--set',r['avant']['demarrage'])
        executer(r['avant']['actif']+'/bin/switch-to-configuration','switch',visible=True)
        services();sauver(d/'retour.json',etat())


def appliquer(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger(etat()==r['avant'] and not (d/'retour-engage').exists(),'État modifié ou retour engagé')
        executer(r['candidat']+'/bin/switch-to-configuration','test',visible=True)
        services();sauver(d/'essai.json',etat())


def demarrer(revision):
    d,r=lire(revision)
    exiger(not any((d/n).exists() for n in ('engage','retour-engage','enregistre')),'Opération déjà engagée')
    exiger(etat()==r['avant'],'État modifié depuis la préparation : nouvel audit nécessaire')
    (d/'engage').touch()
    script=d/'source/scripts/mcp-deployer.py'
    executer('systemd-run','--unit=mcp-retour-'+revision[:12],'--on-active=20m',
             '--timer-property=AccuracySec=1s','--setenv=PATH='+os.environ['PATH'],r['python'],script,'retour',revision)
    executer('systemctl','is-active','mcp-retour-'+revision[:12]+'.timer')
    executer('systemd-run','--wait','--pipe','--unit=mcp-appliquer-'+revision[:12],
             '--setenv=PATH='+os.environ['PATH'],r['python'],script,'appliquer',revision,visible=True)


def finaliser(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger((d/'essai.json').exists() and not (d/'retour-engage').exists(),'Essai absent ou retour engagé')
        courant=etat();exiger(courant['actif']==r['candidat'],'Génération différente')
        exiger(all(courant[k]==v for k,v in r['avant'].items() if k!='actif'),'Changement concurrent')
        services()
        temporaire=ENTREE.with_suffix('.mcp')
        temporaire.write_text('{ imports = [ '+r['configuration']+' ]; }\n');temporaire.chmod(0o644)
        os.replace(temporaire,ENTREE)
        executer('nix-env','--profile','/nix/var/nix/profiles/system','--set',r['candidat'])
        executer(r['candidat']+'/bin/switch-to-configuration','boot',visible=True)
        exiger(etat()['demarrage']==r['candidat'],'Démarrage non enregistré')
        services();sauver(d/'termine.json',{'revision':revision,'etat':etat()})
        (d/'enregistre').touch()
    executer('systemctl','stop','mcp-retour-'+revision[:12]+'.timer')


if __name__=='__main__':
    exiger(os.geteuid()==0,'Exécution réservée au runner administratif')
    os.umask(0o077)
    {'preparer':preparer,'demarrer':demarrer,'appliquer':appliquer,'retour':retour,
     'finaliser':finaliser}[sys.argv[1]](sys.argv[2])
