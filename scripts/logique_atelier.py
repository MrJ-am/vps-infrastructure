#!/usr/bin/env python3
"""Publication statique bornée de Logique : artefact exact, retour autonome, aucune migration."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from corrections_artefacts import lire as lire_artefact
from logique_artefact import exiger, exiger_publication

RACINE = Path('/root/logique-atelier')
SOURCE = Path(__file__).resolve().parents[1]
PROJETS = ('logique','vision','vision-interface','matheval')


def executer(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT)


def empreinte(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sauver(path, valeur):
    provisoire=path.with_suffix('.tmp')
    provisoire.write_text(json.dumps(valeur,ensure_ascii=False,indent=2)+'\n')
    os.replace(provisoire,path)


def etat():
    return {'systeme':str(Path('/run/current-system').resolve()),
            'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
            'configuration':empreinte('/etc/nixos/configuration.nix'),
            **{p:str(Path('/srv',p,'current').resolve()) for p in PROJETS}}


def services():
    executer('systemctl','is-active','nginx','sshd','postgresql','matheval','vision','mrj-auth',
             'postgresqlBackup-matheval.timer','postgresqlBackup-vision.timer')


def verifier(source=SOURCE):
    reference=json.loads((source/'operations/logique-atelier-candidat.json').read_text())
    exiger(reference['ci']['conclusion']=='success' and reference['ci']['revision']==reference['application'],
           'CI exacte de Logique non validée')
    exiger(type(reference['ci']['execution']) is int, 'Exécution CI absente')
    for cle in ('application','style','signature'):
        exiger(re.fullmatch('[0-9a-f]{40}',reference[cle]),'Révision exacte requise : '+cle)
    manifeste,fichiers=lire_artefact(source,'logique',reference,repertoire='logique-atelier')
    exiger({'atelier.js','atelier.css','app.js','course.js','bridge.js','video.js'} <= set(fichiers),
           'Ressources de l’atelier absentes')
    return reference,manifeste,fichiers


def dossier(revision):
    exiger(re.fullmatch('[0-9a-f]{40}',revision),'Révision opérateur exacte requise')
    return RACINE/revision


def lire(revision):
    d=dossier(revision)
    return d,json.loads((d/'preparation.json').read_text())


def inventaire(cible):
    fichiers={}
    for p in Path(cible).rglob('*'):
        exiger(not p.is_symlink(),'Lien interdit dans l’artefact statique')
        if p.is_file(): fichiers[str(p.relative_to(cible))]=empreinte(p)
    return fichiers


def attendu(preparation):
    return {**preparation['avant'],'logique':preparation['publication']}


def controler_fichiers(preparation):
    exiger(inventaire(Path(preparation['publication']))==preparation['fichiers'],'Artefact statique altéré')


def lien(cible,courant):
    temporaire=courant.with_name(courant.name+'.atelier-provisoire')
    exiger(not temporaire.exists() and not temporaire.is_symlink(),'Bascule temporaire déjà présente')
    temporaire.symlink_to(cible)
    os.replace(temporaire,courant)


def preparer(revision):
    d=dossier(revision)
    exiger(not (d/'preparation.json').exists(),'Opération déjà préparée')
    avant=etat();services()
    exiger(avant['systeme']==avant['demarrage'],'Générations désynchronisées')
    exiger(Path('/srv/logique/current').is_symlink(),'Publication Logique actuelle non identifiée')
    reference,manifeste,fichiers=verifier(d/'source')
    publication=Path('/srv/logique/releases')/reference['application']
    exiger(str(publication)!=avant['logique'],'Candidat déjà actif')
    exiger(not publication.exists(),'Une release portant cette identité existe déjà ; ne pas la réécrire')
    publication.mkdir(mode=0o755)
    for nom,contenu in fichiers.items():
        p=publication/nom
        exiger(p.resolve().is_relative_to(publication.resolve()),'Chemin hors publication')
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(contenu)
    manifeste={**manifeste,'hebergementConfirme':True,'publicationAutorisee':True,'preuveInfrastructure':revision}
    exiger_publication(manifeste)
    sauver(publication/'manifeste-preparation.json',manifeste)
    executer('chmod','-R','a+rX',str(publication))
    temoin=d/'temoin-retour'
    executer('systemd-run','--unit=logique-atelier-temoin-'+revision[:12],
             '--on-active=2s','--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',str(temoin))
    for _ in range(15):
        if temoin.exists():break
        time.sleep(1)
    exiger(temoin.exists(),'Le mécanisme de retour autonome ne répond pas')
    exiger(etat()==avant,'État actif changé pendant la préparation')
    preparation={'revision':revision,'avant':avant,'publication':str(publication),
                 'application':reference['application'],'python':sys.executable,'fichiers':inventaire(publication)}
    sauver(d/'preparation.json',preparation)
    print(json.dumps({**preparation,'activation':False},ensure_ascii=False))


def demarrer(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger(not (d/'engage').exists() and not (d/'enregistre').exists(),'Cette activation a déjà été engagée')
        exiger(etat()==r['avant'],'État changé depuis l’audit de préparation')
        controler_fichiers(r);services()
        executer('systemd-run','--unit=logique-atelier-retour-'+revision[:12],
                 '--on-active=10min','--timer-property=AccuracySec=1s',r['python'],
                 str(d/'source/scripts/logique_atelier.py'),'retour',revision)
        executer('systemctl','is-active','logique-atelier-retour-'+revision[:12]+'.timer')
        (d/'engage').touch()
        lien(r['publication'],Path('/srv/logique/current'))
        exiger(etat()==attendu(r),'État inattendu après la bascule statique')
        services();sauver(d/'essai.json',etat())
    print('Logique activé sous retour autonome ; contrôle HTTPS encore obligatoire.')


def retour(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        if (d/'enregistre').exists():return
        exiger((d/'engage').exists(),'Activation non engagée')
        courant=etat()
        exiger(courant['logique'] in (r['avant']['logique'],r['publication']),
               'Une publication concurrente de Logique interdit ce retour')
        lien(r['avant']['logique'],Path('/srv/logique/current'))
        sauver(d/'retour.json',{'etat':etat(),'restauration_base':False,'ancienne_release_conservee':True})
    subprocess.run(['systemctl','stop','logique-atelier-retour-'+revision[:12]+'.timer'],check=False)


def finaliser(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger((d/'essai.json').exists() and not (d/'retour.json').exists(),'Essai absent ou déjà annulé')
        exiger(etat()==attendu(r),'Les invariants ont changé')
        controler_fichiers(r);services()
        (d/'enregistre').touch()
    executer('systemctl','stop','logique-atelier-retour-'+revision[:12]+'.timer')
    constater(revision)


def constater(revision):
    d,r=lire(revision)
    exiger((d/'enregistre').exists() and not (d/'retour.json').exists(),'Publication non finalisée')
    exiger(etat()==attendu(r),'État final différent de la publication contrôlée')
    controler_fichiers(r);services()
    retourActif=subprocess.run(['systemctl','is-active','--quiet','logique-atelier-retour-'+revision[:12]+'.timer']).returncode==0
    exiger(not retourActif,'Retour autonome encore actif')
    preuve={'operateur':revision,'application':r['application'],'etat':etat(),'ancienne_release':r['avant']['logique'],
            'fichiers_verifies':len(r['fichiers']),'retour_autonome_actif':False,
            'migration_sql':False,'reconstruction_nixos':False,'autres_publications_conservees':True}
    sauver(d/'constat.json',preuve)
    print(json.dumps(preuve,ensure_ascii=False,indent=2))


if __name__=='__main__':
    commande=sys.argv[1]
    if commande=='verifier':
        reference,_,fichiers=verifier()
        print(json.dumps({'application':reference['application'],'fichiers':len(fichiers)}))
    else:
        exiger(commande in ('preparer','demarrer','retour','finaliser','constater'),'Opération inconnue')
        globals()[commande](sys.argv[2])
