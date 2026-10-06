#!/usr/bin/env python3
"""Publier le serveur et la vitrine exacts sans migration ni restauration métier.
Les anciennes releases restent en place. Le retour ne change que deux liens et
le service Vision ; les données, les fonctions SQL et NixOS sont conservés.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
import urllib.request

RACINE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publication_vision',RACINE/'scripts/vision-autonomie-deployer.py')
commun=importlib.util.module_from_spec(spec);spec.loader.exec_module(commun)
exiger=commun.exiger
executer=commun.executer
sauver=commun.sauver
empreinte=commun.empreinte
etat=commun.etat
services=commun.services
psql=commun.psql


def dossier(revision):
    exiger(re.fullmatch('[0-9a-f]{40}',revision),'Révision exacte requise')
    return Path('/root/vision-vitrine-operations')/revision


def donnees(base):
    """Comparer tous les champs et toutes les tables, uniquement pendant l’arrêt."""
    tables=psql(base,"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' ORDER BY tablename").decode().splitlines()
    exiger(tables and all(re.fullmatch('vision_[a-z_]+',t) for t in tables),'Tables absentes ou inattendues')
    return {t:psql(base,"SELECT md5(coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text FROM "+t+" t),'[]'))").decode().strip() for t in tables}


def contrat(base):
    exiger(psql(base,'SELECT vision_revision_contrat(); SELECT vision_creation_contrat()').strip()==b'7\n1','Contrat SQL différent de 7/1')


def restaurer_copie(d,backup):
    """Essayer la sauvegarde dans une base jetable. La production reste en ligne."""
    base='vision_vitrine_'+uuid.uuid4().hex[:16]
    temporaire=Path('/var/lib/postgresql')/(base+'.dump')
    toc_prive=Path('/var/lib/postgresql')/(base+'.list')
    executer('runuser','-u','postgres','--','createdb','-h','/run/postgresql','-O','vision',base)
    try:
        executer('runuser','-u','postgres','--','psql','-XAtq','-v','ON_ERROR_STOP=1','-d',base,'-c','CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;')
        toc=executer('pg_restore','--list',backup).decode()
        toc_prive.write_text('\n'.join(l for l in toc.splitlines() if not re.search(r' (?:EXTENSION|COMMENT - EXTENSION) ',l))+'\n')
        shutil.copyfile(backup,temporaire)
        for fichier in (temporaire,toc_prive):
            executer('chown','postgres:postgres',fichier);fichier.chmod(0o600)
        executer('runuser','-u','postgres','--','pg_restore','--exit-on-error','--no-owner','--role=vision','-h','/run/postgresql','-d',base,'--use-list='+str(toc_prive),temporaire)
        contrat(base)
        return base
    except BaseException:
        executer('runuser','-u','postgres','--','dropdb','-h','/run/postgresql',base)
        raise
    finally:
        temporaire.unlink(missing_ok=True);toc_prive.unlink(missing_ok=True)


def essayer_serveur(cible,base,url_mcp):
    """Lire le candidat sur une copie restaurée, sans passer par la production."""
    import socket
    with socket.socket() as adresse:
        adresse.bind(('127.0.0.1',0));port=adresse.getsockname()[1]
    with (cible/'essai-prive.log').open('wb') as journal:
        # Le compte Unix vision ne peut se connecter qu’à sa base de production.
        # La copie jetable passe par le pair postgres, avec SET ROLE dès la
        # connexion. Les requêtes gardent les droits SQL de vision et aucune
        # règle d’accès de production n’est élargie pour permettre le test.
        # Le groupe supplémentaire donne seulement la traversée des releases
        # protégées. Aucun compte ni permission de fichier n’est modifié.
        processus=subprocess.Popen(['runuser','-u','postgres','-g','postgres','-G','vision','--',str(cible/'vision')],
            cwd=cible,
            env={**os.environ,'IP':'127.0.0.1','PORT':str(port),'PGHOST':'/run/postgresql','PGDATABASE':base,'PGUSER':'postgres','PGOPTIONS':'-c role=vision','VISION_DOCUMENT_ROOT':str(cible/'docs')},
            stdout=journal,stderr=journal)
        try:
            origine='http://127.0.0.1:'+str(port)
            for _ in range(80):
                try:
                    with urllib.request.urlopen(origine+'/healthz',timeout=1) as r:
                        exiger(json.load(r)['version']=='2.6.1','Version candidate différente');break
                except OSError:
                    exiger(processus.poll() is None,'Serveur candidat arrêté');time.sleep(.1)
            else:raise RuntimeError('Serveur candidat indisponible')
            with urllib.request.urlopen(origine+'/mcp-config.json',timeout=5) as r:
                exiger(json.load(r)['url_mcp']==url_mcp,'Adresse MCP candidate différente')
            demande=urllib.request.Request(origine+'/api/v1/tutoriel',data=b'{}',headers={'Content-Type':'application/json','X-Vision-Authenticated':'1','X-Mrj-User':'verification-vitrine'})
            with urllib.request.urlopen(demande,timeout=10) as r:
                exiger(len(json.load(r)['sections'])==11,'Tutoriel candidat incomplet')
        finally:
            processus.terminate();processus.wait(timeout=5)


def preparer(revision):
    d=dossier(revision);src=d/'source';demande=json.loads((src/'operations/vision-vitrine-candidat.json').read_text())
    executer(sys.executable,src/'scripts/vision-vitrine-candidat.py')
    avant=etat();services();contrat('vision')
    exiger(not (d/'preparation.json').exists(),'Opération déjà préparée')
    exiger(avant==demande['avant'],'État différent de l’audit lié au candidat')
    for n,h in demande['fichiers'].items():exiger(empreinte(src/n)==h,'Archive candidate différente')
    app=demande['application'];exiger(re.fullmatch('[0-9a-f]{40}',app),'Révision applicative invalide')
    cible=Path('/srv/vision/releases')/(app+'-'+revision[:12])
    exiger(not cible.exists(),'Release déjà présente')
    cible.mkdir(mode=0o755,parents=True);commun.decompresser(cible,src/'vendor/vision-vitrine-source.tar.gz')
    exiger((cible/'revision-application.txt').read_text().strip()==app,'Source différente')
    nixpkgs=executer('nix-instantiate','--find-file','nixpkgs').decode().strip()
    executer('nix-shell','-I','nixpkgs='+nixpkgs,'-p','sbcl','--run','cd '+shlex.quote(str(cible))+' && sh build.sh')
    exiger((cible/'vision').stat().st_size>1000000,'Binaire absent')
    projet=json.loads((src/'projects.json').read_text())['vision']
    exiger(re.fullmatch('[a-zA-Z0-9.-]+',projet['domain']) and re.fullmatch('/[a-zA-Z0-9/_-]*|',projet['prefix']),'Routage invalide')
    url_mcp='https://'+projet['domain']+projet['prefix']+'/mcp'
    (cible/'vision').rename(cible/'vision-lisp')
    (cible/'vision').write_text('#!/bin/sh\nexport VISION_PUBLIC_MCP_URL='+shlex.quote(url_mcp)+'\nexec '+shlex.quote(str(cible/'vision-lisp'))+' "$@"\n')
    (cible/'vision').chmod(0o755);executer('chmod','-R','a+rX',cible)
    statique=commun.interface(d,src/'vendor/vision-vitrine-interface.zip',app)
    manifeste=json.loads((Path(statique)/'manifest.json').read_text())
    exiger(manifeste['revisionStyle']==demande['style'],'Style différent du candidat validé')
    backup=commun.sauvegarder(d,'preparation')
    base=restaurer_copie(d,backup)
    try:
        avant_copie=donnees(base);essayer_serveur(cible,base,url_mcp)
        exiger(donnees(base)==avant_copie,'Le démarrage a modifié la copie de sauvegarde')
    finally:executer('runuser','-u','postgres','--','dropdb','-h','/run/postgresql',base)
    temoin=d/'timer-verifie'
    executer('systemd-run','--unit=vision-vitrine-temoin-'+revision[:12],'--on-active=2s','--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',temoin)
    for _ in range(15):
        if temoin.exists():break
        time.sleep(1)
    exiger(temoin.exists(),'Timer autonome non vérifié')
    racine_python=Path(*Path(sys.executable).parts[:4])
    exiger(str(racine_python).startswith('/nix/store/'),'Python de retour non fixé')
    executer('nix-store','--add-root','/nix/var/nix/gcroots/vision-vitrine-'+revision[:12]+'-python','--realise',racine_python)
    exiger(etat()==avant,'État modifié pendant la préparation');services()
    rapport=dict(version='2.6.1',audit=demande['audit'],migrations=[],contrat_sql=7,creation_items=1,
        restauration_verifiee=True,demarrage_copie_sans_ecriture=True,timer_verifie=True,sauvegarde_sha256=empreinte(backup),sauvegarde_octets=backup.stat().st_size)
    sauver(d/'preparation.json',dict(revision=revision,application=app,avant=avant,serveur=str(cible),interface=statique,python=sys.executable,rapport=rapport))
    sauver(d/'preparation-rapport.json',rapport);print(json.dumps(rapport))


def lire(revision):
    d=dossier(revision);return d,json.loads((d/'preparation.json').read_text())


def appliquer(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger(etat()==r['avant'] and not (d/'retour-engage').exists(),'État modifié depuis la préparation')
        executer('systemctl','stop','vision')
        avant=donnees('vision');contrat('vision')
        backup=commun.sauvegarder(d,'activation')
        commun.lien(r['serveur'],'/srv/vision/current');commun.lien(r['interface'],'/srv/vision-interface/current')
        exiger(donnees('vision')==avant,'Données modifiées pendant la bascule')
        executer('systemctl','start','vision');services();contrat('vision')
        rapport={**r['rapport'],'donnees_preservees':True,'tables_preservees':len(avant),'sauvegarde_activation_sha256':empreinte(backup),'ecritures_metier_production':0,'restauration_production':False}
        sauver(d/'essai.json',dict(etat=etat(),rapport=rapport))
    print('Serveur et vitrine activés. Aucun changement SQL ou système.')


def retour(revision):
    d,r=lire(revision)
    if (d/'enregistre').exists():return
    subprocess.run(['systemctl','stop','vision-vitrine-appliquer-'+revision[:12]],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        if (d/'enregistre').exists():return
        exiger((d/'engage').exists(),'Aucune activation engagée')
        courant=etat()
        exiger(all(courant[k]==r['avant'][k] for k in ('systeme','demarrage','configuration','matheval','logique')),'État système ou voisin modifié')
        exiger(courant['vision'] in (r['avant']['vision'],r['serveur']) and courant['vision-interface'] in (r['avant']['vision-interface'],r['interface']),'Publication concurrente')
        (d/'retour-engage').touch();executer('systemctl','stop','vision')
        avant=donnees('vision')
        commun.lien(r['avant']['vision'],'/srv/vision/current');commun.lien(r['avant']['vision-interface'],'/srv/vision-interface/current')
        exiger(donnees('vision')==avant,'Données modifiées pendant le retour')
        executer('systemctl','start','vision');services();contrat('vision')
        sauver(d/'retour.json',dict(etat=etat(),restauration_base=False,donnees_preservees=True))
    executer('systemctl','stop','vision-vitrine-retour-'+revision[:12]+'.timer')


def demarrer(revision):
    d,r=lire(revision)
    exiger(not any((d/n).exists() for n in ('engage','retour-engage','enregistre')),'Opération déjà engagée')
    exiger(etat()==r['avant'],'Nouvel audit nécessaire');(d/'engage').touch()
    script=d/'source/scripts/vision-vitrine-deployer.py'
    executer('systemd-run','--unit=vision-vitrine-retour-'+revision[:12],'--on-active=20m','--timer-property=AccuracySec=1s','--setenv=PATH='+os.environ['PATH'],r['python'],script,'retour',revision)
    executer('systemctl','is-active','vision-vitrine-retour-'+revision[:12]+'.timer')
    executer('systemd-run','--wait','--pipe','--unit=vision-vitrine-appliquer-'+revision[:12],'--setenv=PATH='+os.environ['PATH'],r['python'],script,'appliquer',revision)


def finaliser(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger((d/'essai.json').exists() and not (d/'retour-engage').exists(),'Essai absent ou retour engagé')
        exiger(etat()=={**r['avant'],'vision':r['serveur'],'vision-interface':r['interface']},'Publication différente');services();contrat('vision')
        sauver(d/'termine.json',dict(revision=revision,application=r['application'],etat=etat(),rapport=json.loads((d/'essai.json').read_text())['rapport']))
        (d/'enregistre').touch()
    executer('systemctl','stop','vision-vitrine-retour-'+revision[:12]+'.timer')
    print('Publication enregistrée. Retour désarmé ; anciennes releases conservées.')


if __name__=='__main__':
    exiger(os.geteuid()==0,'Exécution réservée au runner administratif');os.umask(0o077)
    os.environ['VISION_AUTONOMIE_ERREURS']=str(dossier(sys.argv[2])/'commande-echec-prive.log')
    {'preparer':preparer,'demarrer':demarrer,'appliquer':appliquer,'retour':retour,'finaliser':finaliser}[sys.argv[1]](sys.argv[2])
