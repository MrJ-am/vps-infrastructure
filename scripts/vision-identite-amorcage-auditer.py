"""Diagnostic du seul essai identifié ; jamais d'extrait privé dans la sortie."""
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = '88dc20580cbfc3e790eb19f366794b8b94f87e9d'
DOSSIER = Path('/root/vision-identite-amorcage-essais')/REVISION
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


def etat_worker(outils):
    unite = 'vision-amorcage-essai-' + REVISION[:12] + '.service'
    r = subprocess.run([str(outils/'systemctl'),'show',unite,'--property=ActiveState',
        '--property=ExecMainStatus'], capture_output=True, timeout=5)
    valeurs = dict(l.split('=',1) for l in r.stdout.decode().splitlines() if '=' in l)
    if r.returncode or valeurs.get('ActiveState') not in ('inactive','failed') or not re.fullmatch(r'[0-9]{1,3}',valeurs.get('ExecMainStatus','')) or int(valeurs['ExecMainStatus']) > 255:
        raise ValueError('Worker non arrêté ou état indéterminé')
    journal = subprocess.run([str(outils/'journalctl'),'--unit='+unite,'--lines=120',
        '--output=cat','--no-pager'], capture_output=True, timeout=10)
    if journal.returncode or len(journal.stdout)>1048576: raise ValueError('Journal technique indisponible')
    return dict(etat=valeurs['ActiveState'], code=int(valeurs['ExecMainStatus'])), journal.stdout.decode(errors='replace')


def main():
    if os.geteuid() != 0: raise ValueError('Audit root Actions requis')
    for path in (DOSSIER.parent, DOSSIER):
        s = path.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('Dossier privé requis')
    spec = importlib.util.spec_from_file_location('construction', ROOT/'scripts/vision-identite-construire.py')
    construction = importlib.util.module_from_spec(spec); spec.loader.exec_module(construction)
    candidat = json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
    construction.verifier_socle(candidat)
    marqueurs = {nom:(DOSSIER/nom).exists() for nom in ('commence','plan.json','enregistre','retour-commence','retour-termine')}
    verifier_retour(marqueurs)
    for nom,present in marqueurs.items():
        if present: lire(DOSSIER/nom)
    diagnostic = lire(DOSSIER/'diagnostic-prive.log'); dry = lire(DOSSIER/'dry-activate-prive.txt')
    worker = lire(DOSSIER/'worker-prive.log') if (DOSSIER/'worker-prive.log').exists() else ''
    etat,journal = etat_worker(Path(candidat['audit']['systeme'])/'sw/bin')
    construction.verifier_socle(candidat)
    print(json.dumps(dict(audit_amorcage=2, revision=REVISION, socle_conserve=True,
        retour_termine=True, generation_enregistree=False, activation=False, inscriptions=False,
        worker=etat, controle_worker=classer_worker(worker+'\n'+journal),
        cluster_prive_present=Path('/var/lib/mrjam-amorcage-postgresql').exists(),
        **classer(diagnostic,dry)), ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps(dict(audit_amorcage=1, diagnostic_refuse=True, activation=False)))
        raise SystemExit(1)
