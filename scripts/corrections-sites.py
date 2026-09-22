#!/usr/bin/env python3
"""Activer Logique et actualiser Vision avec retour autonome, sans toucher aux bases."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from corrections_artefacts import verifier
from logique_artefact import exiger, exiger_publication

ENTREE = Path('/etc/nixos/configuration.nix')
SERVICES = ('sshd','nginx','postgresql','matheval','vision','mrj-auth')


def executer(*arguments, visible=False):
    return subprocess.run([str(a) for a in arguments], check=True, text=True,
                          stdout=None if visible else subprocess.PIPE).stdout


def enregistrer(chemin, contenu):
    temporaire = chemin.with_suffix('.nouveau')
    temporaire.write_text(json.dumps(contenu, ensure_ascii=False, indent=2)+'\n')
    os.replace(temporaire, chemin)


def dossier(revision):
    exiger(re.fullmatch('[0-9a-f]{40}', revision), 'Révision exacte requise')
    return Path('/root/logique-preparations')/revision


def services():
    executer('systemctl','is-active',*SERVICES,'postgresqlBackup-matheval.timer','postgresqlBackup-vision.timer')


def etat():
    return {'actif':str(Path('/run/current-system').resolve()),
            'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
            'configuration':hashlib.sha256(ENTREE.read_bytes()).hexdigest(),
            **{p:str(Path('/srv/'+p+'/current').resolve()) if Path('/srv/'+p+'/current').is_symlink() else None
               for p in ('matheval','vision','vision-interface','logique')}}


def lien(projet, cible):
    courant=Path('/srv/'+projet+'/current')
    temporaire=courant.with_name('suivant-corrections')
    temporaire.unlink(missing_ok=True)
    temporaire.symlink_to(cible)
    os.replace(temporaire,courant)


def preparer(revision):
    d=dossier(revision);source=d/'source';avant=etat()
    exiger(avant['vision-interface'] is not None and avant['logique'] is None, 'État initial inattendu')
    artefacts=verifier(source)
    executer(sys.executable,source/'scripts/logique-preparer.py',revision,visible=True)
    preparation=json.loads((d/'preparation.json').read_text())
    for phase,candidat in preparation['candidats'].items():
        simulation=subprocess.run([str(Path(candidat['systeme'])/'bin/switch-to-configuration'),'dry-activate'],
                                  check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout
        (d/('simulation-'+phase+'.txt')).write_text(simulation)
        print(phase+' : '+simulation,flush=True)
    publications={}
    for projet,(manifeste,fichiers) in artefacts.items():
        application=manifeste['application' if projet=='logique' else 'revisionApplication']
        cible=Path('/srv/'+('logique' if projet=='logique' else 'vision-interface')+'/releases')/application
        exiger(not cible.exists(), 'Publication déjà présente : nouvelle vérification nécessaire')
        cible.mkdir(parents=True)
        for nom,contenu in fichiers.items():
            p=cible/nom;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(contenu)
        # Les sources restent privées ; seuls les fichiers statiques deviennent lisibles.
        for p in [cible.parent.parent,cible.parent,cible,*cible.rglob('*')]:
            p.chmod(0o755 if p.is_dir() else 0o644)
        publications[projet]=str(cible)
    for projet in ('matheval','vision'):
        with (d/(projet+'-avant.dump.age')).open('wb') as sortie:
            subprocess.run([projet+'-backup'],stdout=sortie,check=True)
    executer(sys.executable,source/'scripts/probe.py','--output',d/'http-avant.json',visible=True)
    temoin=d/'timer-verifie'
    executer('systemd-run','--unit=corrections-temoin-'+revision[:12],'--on-active=2s',
             '--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',temoin)
    for _ in range(15):
        if temoin.exists():break
        time.sleep(1)
    exiger(temoin.exists(),'Déclenchement autonome non vérifié')
    exiger(etat()==avant,'État modifié pendant la préparation')
    services()
    enregistrer(d/'corrections.json',{'revision':revision,'avant':avant,'publications':publications,
                                    'preparation':preparation,'python':sys.executable})
    print('Deux générations et deux artefacts préparés ; aucun lien actif modifié.')


def lire(revision):
    d=dossier(revision)
    return d,json.loads((d/'corrections.json').read_text())


def retour(revision):
    d,r=lire(revision)
    subprocess.run(['systemctl','stop','corrections-appliquer-'+revision[:12]],check=False)
    with (d/'finaliser.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        if (d/'enregistre').exists():return
        exiger((d/'demarrage-engage').exists(),'Aucune bascule engagée')
        autorises=[r['avant']['actif'],*[v['systeme'] for v in r['preparation']['candidats'].values()]]
        exiger(etat()['actif'] in autorises,'Une autre génération est active : retour refusé')
        (d/'retour-engage').touch()
        # Restaurer les fichiers servis avant Nginx, sans restaurer les données.
        lien('vision-interface',r['avant']['vision-interface'])
        courant=Path('/srv/logique/current')
        if courant.is_symlink() and str(courant.resolve())==r['publications']['logique']:courant.unlink()
        executer('sh',r['preparation']['retour'],visible=True)
        services()
        enregistrer(d/'retour.json',{'etat':etat(),'retabli':True})


def appliquer(revision):
    d,r=lire(revision)
    verrous=[]
    for projet in ('matheval','vision'):
        verrou=open('/srv/'+projet+'/deploy.lock','a');fcntl.flock(verrou,fcntl.LOCK_EX);verrous.append(verrou)
    with (d/'finaliser.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger(etat()==r['avant'] and not (d/'retour-engage').exists(),'État différent ou retour engagé')
        artefacts=verifier(d/'source')
        for projet,(_,fichiers) in artefacts.items():
            for nom,contenu in fichiers.items():
                exiger((Path(r['publications'][projet])/nom).read_bytes()==contenu,'Publication modifiée')
        candidats=r['preparation']['candidats']
        executer(Path(candidats['acme']['systeme'])/'bin/switch-to-configuration','test',visible=True)
        services()
        executer('systemctl','start','acme-logique.echos.systems.service',visible=True)
        # Un vrai certificat est exigé par le contrôle HTTPS extérieur du workflow.
        executer(*shlex.split(candidats['https']['nginx']),'-t',visible=True)
        manifeste=dict(artefacts['logique'][0])
        # Nouvelle étape attestée : DNS exigé par le workflow, candidat Nginx construit,
        # toutes les CI réussies, publication demandée par le propriétaire le 22/09.
        manifeste.update(hebergementConfirme=True,publicationAutorisee=True,preuveInfrastructure=revision)
        exiger_publication(manifeste)
        enregistrer(Path(r['publications']['logique'])/'manifeste-preparation.json',manifeste)
        (Path(r['publications']['logique'])/'manifeste-preparation.json').chmod(0o644)
        lien('logique',r['publications']['logique']);lien('vision-interface',r['publications']['vision'])
        executer(Path(candidats['https']['systeme'])/'bin/switch-to-configuration','test',visible=True)
        services()
        enregistrer(d/'essai.json',{'etat':etat(),'logique':manifeste})


def demarrer(revision):
    d,r=lire(revision)
    exiger(not any((d/n).exists() for n in ('demarrage-engage','retour-engage','enregistre')),'Opération déjà engagée')
    exiger(etat()==r['avant'],'État modifié : nouvel audit nécessaire')
    exiger(hashlib.sha256(Path(r['preparation']['retour']).read_bytes()).hexdigest()==r['preparation']['empreinteRetour'],'Retour modifié')
    (d/'demarrage-engage').touch()
    script=d/'source/scripts/corrections-sites.py'
    executer('systemd-run','--unit=corrections-retour-'+revision[:12],'--on-active=20m',
             '--timer-property=AccuracySec=1s','--setenv=PATH='+os.environ['PATH'],r['python'],script,'retour',revision)
    executer('systemctl','is-active','corrections-retour-'+revision[:12]+'.timer')
    executer('systemd-run','--wait','--pipe','--unit=corrections-appliquer-'+revision[:12],
             '--setenv=PATH='+os.environ['PATH'],r['python'],script,'appliquer',revision,visible=True)


def finaliser(revision):
    d,r=lire(revision);candidat=r['preparation']['candidats']['https']
    with (d/'finaliser.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger((d/'essai.json').exists() and not (d/'retour-engage').exists(),'Essai absent ou retour engagé')
        courant=etat()
        exiger(courant['actif']==candidat['systeme'],'Génération différente')
        exiger(courant['logique']==r['publications']['logique'] and courant['vision-interface']==r['publications']['vision'],'Liens différents')
        exiger(all(courant[n]==r['avant'][n] for n in ('demarrage','configuration','matheval','vision')),'Changement concurrent')
        services()
        temporaire=ENTREE.with_suffix('.corrections')
        temporaire.write_text('{ imports = [ '+candidat['configuration']+' ]; }\n');temporaire.chmod(0o644)
        os.replace(temporaire,ENTREE)
        executer('nix-env','--profile','/nix/var/nix/profiles/system','--set',candidat['systeme'])
        executer(Path(candidat['systeme'])/'bin/switch-to-configuration','boot',visible=True)
        exiger(etat()['demarrage']==candidat['systeme'],'Démarrage non enregistré')
        services()
        enregistrer(d/'termine.json',{'revision':revision,'etat':etat()})
        (d/'enregistre').touch()
    executer('systemctl','stop','corrections-retour-'+revision[:12]+'.timer')


if __name__=='__main__':
    exiger(os.geteuid()==0,'Exécution VPS réservée au runner administratif')
    os.umask(0o077)
    {'preparer':preparer,'demarrer':demarrer,'appliquer':appliquer,'finaliser':finaliser,'retour':retour}[sys.argv[1]](sys.argv[2])
