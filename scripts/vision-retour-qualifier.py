"""Qualifier les conditions systemd sur une unité jetable, sans basculer Vision."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREPARATION='a2509f53ea44e91efb83f8b1ff936e4ab5e78e36'
ETAPE='demarrage'


def etape(nom):
    global ETAPE
    ETAPE=nom
    print(json.dumps(dict(etape_retour=nom)),flush=True)


def exiger(condition):
    if not condition:raise ValueError('Qualification du retour refusée')


def charger(nom,fichier):
    s=importlib.util.spec_from_file_location(nom,fichier)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def qualifier(revision):
    exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision))
    os.umask(0o077)
    d=Path('/root/vision-retour-qualifications')/revision
    exiger(ROOT==d/'source')
    prive=charger('prive_retour',ROOT/'scripts/identite-preparer.py')
    construction=charger('construction_retour',ROOT/'scripts/vision-identite-construire.py')
    for p in (d.parent,d,ROOT):construction.dossier_prive(p)
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:prive.ecrire(fd,'commence','1\n')
    finally:os.close(fd)
    etape('preparation_exacte')
    ancien=Path('/root/vision-bascule-preparations')/PREPARATION
    construction.dossier_prive(ancien)
    fd=os.open(ancien,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        r=json.loads(prive.lire(fd,'essai-preparation.json'))
        e=json.loads(prive.lire(fd,'evaluation-essai.json'))
    finally:os.close(fd)
    public=json.loads((ROOT/'operations/vision-essai-preparation-reelle.json').read_text())
    exiger(r['infrastructure']==PREPARATION and all(public.get(k)==v for k,v in r.items()))
    exiger(all(r[k] is True for k in ('generation_complete_construite','dry_activate_qualifie',
        'configuration_nginx_native','entree_persistante_reproduite','timer_independant_repete',
        'retour_acl_rejoue','association_et_admin_isoles','copie_exterieure_verifiee')))
    exiger(all(r[k] is False for k in ('generation_active_modifiee','donnees_production_modifiees',
        'retour_autonome_arme','activation','inscriptions')))
    exiger(Path('/run/current-system').resolve()==Path(e['systeme_actif']))
    exiger(Path('/nix/var/nix/profiles/system').resolve()==Path(e['systeme_actif']))
    construction.store(e['systeme_candidat'])
    exiger(Path(e['systeme_candidat']).is_dir())
    association=charger('association_retour',ROOT/'scripts/vision-bascule-principaux.py')
    preparateur=charger('preparateur_retour',ROOT/'scripts/vision-bascule-preparer.py')
    original=Path('/root/vision-proprietaire-operations')/association.OBSERVATION/'source/scripts'
    construction.dossier_prive(original)
    fd=os.open(original,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        exiger(hashlib.sha256(prive.lire(fd,'vision-proprietaire-enroler.py',65536).encode()).hexdigest()==preparateur.OBSERVER_HASH)
    finally:os.close(fd)
    observateur=charger('observateur_retour',original/'vision-proprietaire-enroler.py')
    etape('socle_avant')
    observateur.main(association.OBSERVATION,observer=True,activation_seule=True)
    outils=Path(e['systeme_actif'])/'sw/bin'
    diagnostic=d/'diagnostic-prive.log'
    def commande(*a):
        with diagnostic.open('ab') as f:
            z=subprocess.run([str(x) for x in a],stdout=subprocess.PIPE,stderr=f,timeout=40)
            if z.returncode:f.write(z.stdout);f.flush();os.fsync(f.fileno())
        exiger(z.returncode==0)
        return z.stdout.decode().strip()
    unite='vision-retour-condition-'+revision[:12]+'.service'
    etape('condition_native')
    unites=Path('/run/systemd/system')
    exiger(not unites.is_symlink() and unites.is_dir())
    fd=os.open(unites,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:prive.ecrire(fd,unite,'[Unit]\nConditionPathExists=!/\n[Service]\nType=oneshot\nUMask=0077\nExecStart='+
        str(outils/'touch')+' '+str(d/'condition-ne-doit-pas-executer')+'\n')
    finally:os.close(fd)
    try:
        commande(outils/'systemctl','daemon-reload')
        for _ in range(3):
            commande(outils/'systemctl','start',unite)
            exiger(commande(outils/'systemctl','show',unite,'--property=ConditionResult','--value')=='no')
            exiger(commande(outils/'systemctl','show',unite,'--property=ActiveState','--value')=='inactive')
            exiger(not (d/'condition-ne-doit-pas-executer').exists())
    finally:
        # Le seul nom autorisé est propre à cette unité jetable ; aucun service existant.
        subprocess.run([str(outils/'systemctl'),'stop',unite],capture_output=True,timeout=20)
        subprocess.run([str(outils/'systemctl'),'reset-failed',unite],capture_output=True,timeout=20)
        (unites/unite).unlink()
        commande(outils/'systemctl','daemon-reload')
    etape('recette_shell')
    qualification=charger('qualification_retour',ROOT/'scripts/vision-essai-qualification.py')
    q=json.loads((ROOT/'operations/vision-identite-amorcage-qualification.json').read_text())
    base=Path('/root/vision-identite-amorcage-operations')/q['infrastructure']
    construction.dossier_prive(base)
    fd=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:resume=json.loads(prive.lire(fd,'evaluation-privee.json'))
    finally:os.close(fd)
    retour=qualification.script_retour(d,e['systeme_actif'],outils,Path(resume['postgres_paquet']),
        Path(resume['runuser_paquet'])/'bin/runuser','vision-essai-'+revision[:12]+'.service')
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:prive.ecrire(fd,'retour.sh',retour)
    finally:os.close(fd)
    (d/'retour.sh').chmod(0o700)
    commande(outils/'bash','-n',d/'retour.sh')
    etape('socle_apres')
    observateur.main(association.OBSERVATION,observer=True,activation_seule=True)
    exiger(Path('/run/current-system').resolve()==Path(e['systeme_actif']))
    exiger(Path('/nix/var/nix/profiles/system').resolve()==Path(e['systeme_actif']))
    rapport=dict(version=1,infrastructure=revision,preparation=PREPARATION,
        conditions_systemd_natives=True,demarrages_fermes_rejoues=3,
        script_retour_sha256=hashlib.sha256(retour.encode()).hexdigest(),
        recette_retour_syntaxe=True,retour_production_execute=False,
        reprise_apres_redemarrage_machine_qualifiee=False,
        retour_autonome_arme=False,production_modifiee=False,activation=False,inscriptions=False)
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:prive.ecrire(fd,'qualification.json',json.dumps(rapport))
    finally:os.close(fd)
    print(json.dumps(rapport),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('revision');a=p.parse_args()
    try:qualifier(a.revision)
    except Exception as erreur:
        classe=type(erreur).__name__
        if classe not in ('ValueError','FileNotFoundError','PermissionError','KeyError','TimeoutExpired'):
            classe='autre'
        print(json.dumps(dict(qualification_retour_refusee=True,etape=ETAPE,
            classe=classe,activation=False,inscriptions=False)),flush=True)
        raise SystemExit(1)
