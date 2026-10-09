"""Diagnostic du seul essai identifié ; jamais d'extrait privé dans la sortie."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = '88dc20580cbfc3e790eb19f366794b8b94f87e9d'
DERNIERE = 'f9dae92a39f350d5aa5b5795f74b04f6827d60ff'
DOSSIER = Path('/root/vision-identite-amorcage-essais')/REVISION
SCRIPTS = ('vision-identite-amorcage-activer.py','vision-identite-construire.py',
    'vision-multiutilisateur-preparer.py','vision-semantique-socle.py')
UNITES = frozenset(('sshd.service', 'nginx.service', 'postgresql.service', 'vision.service',
    'matheval.service', 'mrj-auth.service', 'nginx-config-reload.service', 'nginx-validate-config.service',
    'systemd-journald.service', 'systemd-journald@identite.service', 'systemd-journald@http.service',
    'systemd-journald@identite.socket', 'systemd-journald-varlink@identite.socket',
    'mrjam-amorcage-postgresql.service', 'mrjam-amorcage-identite.service',
    'mrjam-amorcage-sauvegarde.service', 'mrjam-amorcage-sauvegarde.timer',
    'nix-daemon.service', 'nscd.service', 'systemd-logind.service', 'dbus.service', 'polkit.service',
    'systemd-tmpfiles-setup.service', 'systemd-tmpfiles-resetup.service', 'systemd-sysctl.service',
    'systemd-udevd.service', 'logrotate.service', 'user@0.service', 'user-runtime-dir@0.service'))
MOTIFS = {
    'dry_refuse': r'(?:RuntimeError|ConstructionRefusee): Dry-activate refusé',
    'dry_incomplet': r'(?:RuntimeError|ConstructionRefusee): Dry-activate absent ou incomplet',
    'interruption_socle': r'(?:RuntimeError|ConstructionRefusee): Interruption du socle annoncée',
    'unite_etrangere': r'(?:RuntimeError|ConstructionRefusee): Dry-activate annonce une unité étrangère',
    'permission_refusee': r'Permission denied',
    'systemd_indisponible': r'Failed to connect to (?:system|bus)|System has not been booted with systemd',
    'activation_script_refuse': r'activation script failed|failed to run activation script',
    'lancement_python_refuse': r'Failed at step EXEC|status=203/EXEC|Failed to (?:execute|locate executable)|Exec format error',
    'bibliotheque_python_absente': r'ModuleNotFoundError:',
    'source_operateur_differente': r'(?:RuntimeError|ConstructionRefusee): Source opérateur différente',
    'commande_timeout': r'(?:RuntimeError|ConstructionRefusee): Délai de construction ou de contrôle dépassé',
    'commande_refusee': r'(?:RuntimeError|ConstructionRefusee): Commande de construction ou de contrôle refusée',
    'essai_timeout': r'ValueError: Délai d’essai dépassé',
    'action_masquee': r"getattr\(essai, a\.action\)\(\)[\s\S]{0,1024}TypeError: 'str' object is not callable",
    'nixpkgs_introuvable': r"file 'nixpkgs' was not found|cannot find.*nixpkgs",
    'journal_pg_peer_refuse': r'peer authentication failed',
    'journal_pg_initialisation_refusee': r'initdb: error:',
    'journal_pg_proprietaire_incorrect': r'(?:data directory.*wrong ownership|must be owned by)',
    'journal_db_absente': r'database "mrjam_identite" does not exist',
    'journal_role_absent': r'role "keycloak" does not exist',
    'journal_memoire': r'out of memory|OutOfMemoryError|oom-kill',
}
ETAPES = frozenset(('demarrage', 'essai_generation', 'controles_locaux', 'copie_identite_chiffree'))


def classer(diagnostic, dry):
    unites = {}
    for action, noms in re.findall(r'would (stop|restart|reload) the following units: ([^\n]+)', dry):
        valeurs = {v.strip() for v in noms.split(',')}
        connues = valeurs & UNITES
        acme = {v for v in valeurs if re.fullmatch(r'acme-[A-Za-z0-9_.@-]+\.(?:service|timer|target)', v)}
        unites[action] = dict(connues=sorted(connues), acme=len(acme), inconnues=len(valeurs-connues-acme))
    return dict(categories=[nom for nom,motif in MOTIFS.items() if re.search(motif, diagnostic+'\n'+dry)],
        activation_annoncee='would activate the configuration' in dry,
        redemarrage_systemd='would restart systemd' in dry,
        arret_swap='would stop swap' in dry, unites=unites)


def lire(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1 or s.st_size > 262144:
            raise ValueError('Fichier privé requis')
        contenu = os.read(fd, 262145)
        if len(contenu) > 262144: raise ValueError('Journal trop grand')
        return contenu.decode('utf-8', errors='replace')
    finally: os.close(fd)


def verifier_retour(marqueurs):
    if not all(marqueurs.get(n) is True for n in ('commence','plan.json','retour-commence','retour-termine')) or marqueurs.get('enregistre') is not False:
        raise ValueError('Tentative non retournée : aucune lecture de diagnostic')


def classer_worker(texte):
    etapes = re.findall(r'\{"etape": "([a-z_]+)"\}', texte)
    return dict(etapes=[e for e in etapes if e in ETAPES], **classer(texte, ''))


def verifier_reprise(rapport):
    if (not isinstance(rapport,dict) or rapport.get('revision') != REVISION or
        not all(rapport.get(k) is True for k in ('socle_conserve','retour_termine')) or
        not all(rapport.get(k) is False for k in ('generation_enregistree','activation','inscriptions','cluster_prive_present')) or
        set(rapport.get('categories',[])) != {'action_masquee','essai_timeout'} or
        rapport.get('worker',{}).get('etat') not in ('inactive','failed') or
        rapport.get('controle_worker',{}).get('etapes') != [] or
        rapport.get('controle_worker',{}).get('categories') != []):
        raise ValueError('Cause ou état différents : reprise du worker interdite')


def cadres(texte, source):
    connus={}
    for nom in SCRIPTS:
        p=Path(source)/'scripts'/nom
        if not p.exists(): continue
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_nlink!=1 or s.st_mode&0o022 or s.st_size>131072:
                raise ValueError('Source de diagnostic non conforme')
            code=os.read(fd,131073).decode()
        finally:os.close(fd)
        arbre=ast.parse(code);fonctions={'<module>':[(1,len(code.splitlines()))]}
        for n in ast.walk(arbre):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                fonctions.setdefault(n.name,[]).append((n.lineno,n.end_lineno))
        connus[str(p)]=(nom,fonctions)
    resultat=[]
    for chemin,ligne,fonction in re.findall(r'File "([^"\n]+)", line ([0-9]{1,6}), in ([A-Za-z0-9_]+|<module>)',texte):
        if chemin not in connus:continue
        nom,fonctions=connus[chemin];numero=int(ligne)
        if any(debut<=numero<=fin for debut,fin in fonctions.get(fonction,[])):
            resultat.append(dict(script=nom,fonction=fonction,ligne=numero))
    return resultat[-16:]


def etat_worker(outils, revision=REVISION):
    if revision not in (REVISION,DERNIERE):raise ValueError('Tentative non qualifiée')
    unite = 'vision-amorcage-essai-' + revision[:12] + '.service'
    r = subprocess.run([str(outils/'systemctl'),'show',unite,'--property=ActiveState',
        '--property=ExecMainStatus'], capture_output=True, timeout=5)
    valeurs = dict(l.split('=',1) for l in r.stdout.decode().splitlines() if '=' in l)
    if r.returncode or valeurs.get('ActiveState') not in ('inactive','failed') or not re.fullmatch(r'[0-9]{1,3}',valeurs.get('ExecMainStatus','')) or int(valeurs['ExecMainStatus']) > 255:
        raise ValueError('Worker non arrêté ou état indéterminé')
    journal = subprocess.run([str(outils/'journalctl'),'--unit='+unite,'--lines=120',
        '--output=cat','--no-pager'], capture_output=True, timeout=10)
    if journal.returncode or len(journal.stdout)>1048576: raise ValueError('Journal technique indisponible')
    return dict(etat=valeurs['ActiveState'], code=int(valeurs['ExecMainStatus'])), journal.stdout.decode(errors='replace')


def unites_identite(outils):
    rapports={}
    for nom in ('mrjam-amorcage-postgresql','mrjam-amorcage-identite','mrjam-amorcage-sauvegarde'):
        r=subprocess.run([str(outils/'systemctl'),'show',nom+'.service',
            '--property=ActiveState','--property=ExecMainStatus','--property=Result'],capture_output=True,timeout=5)
        v=dict(l.split('=',1) for l in r.stdout.decode().splitlines() if '=' in l)
        etat=v.get('ActiveState');code=v.get('ExecMainStatus','')
        if r.returncode or etat not in ('active','inactive','failed','activating','deactivating') or not re.fullmatch(r'[0-9]{1,3}',code) or int(code)>255:
            raise ValueError('État d’unité indéterminé')
        resultats=('success','exit-code','signal','timeout','oom-kill','resources','protocol','start-limit-hit')
        resultat=v.get('Result');resultat=resultat if resultat in resultats else 'indetermine'
        j=subprocess.run([str(outils/'journalctl'),'--namespace=identite','--unit='+nom+'.service',
            '--lines=100','--output=cat','--no-pager'],capture_output=True,timeout=10)
        if j.returncode or len(j.stdout)>1048576:raise ValueError('Journal technique indisponible')
        rapports[nom]=dict(etat=etat,code=int(code),resultat=resultat,
            categories=classer(j.stdout.decode(errors='replace'),'')['categories'])
    return rapports


def main(reprise=False):
    if os.geteuid() != 0: raise ValueError('Audit root Actions requis')
    revision=REVISION if reprise else DERNIERE
    dossier=DOSSIER if reprise else DOSSIER.parent/DERNIERE
    for path in (dossier.parent, dossier):
        s = path.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('Dossier privé requis')
    spec = importlib.util.spec_from_file_location('construction', ROOT/'scripts/vision-identite-construire.py')
    construction = importlib.util.module_from_spec(spec); spec.loader.exec_module(construction)
    candidat = json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
    construction.verifier_socle(candidat)
    marqueurs = {nom:(dossier/nom).exists() for nom in ('commence','plan.json','enregistre','retour-commence','retour-termine')}
    verifier_retour(marqueurs)
    for nom,present in marqueurs.items():
        if present: lire(dossier/nom)
    diagnostic = lire(dossier/'diagnostic-prive.log'); dry = lire(dossier/'dry-activate-prive.txt')
    worker = lire(dossier/'worker-prive.log') if (dossier/'worker-prive.log').exists() else ''
    outils=Path(candidat['audit']['systeme'])/'sw/bin'
    etat,journal = etat_worker(outils,revision)
    details={} if reprise else dict(cadres=cadres(diagnostic,dossier/'source'),unites_identite=unites_identite(outils))
    construction.verifier_socle(candidat)
    rapport = dict(audit_amorcage=3, revision=revision, socle_conserve=True,
        retour_termine=True, generation_enregistree=False, activation=False, inscriptions=False,
        worker=etat, controle_worker=classer_worker(worker+'\n'+journal),
        cluster_prive_present=Path('/var/lib/mrjam-amorcage-postgresql').exists(),
        **classer(diagnostic,dry),**details)
    if reprise:
        verifier_reprise(rapport); rapport['reprise_worker_autorisee']=True
    print(json.dumps(rapport, ensure_ascii=False))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--reprise-worker',action='store_true');a=p.parse_args()
    try: main(a.reprise_worker)
    except Exception:
        print(json.dumps(dict(audit_amorcage=1, diagnostic_refuse=True, activation=False)))
        raise SystemExit(1)
