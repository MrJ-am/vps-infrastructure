"""Diagnostic du seul essai identifié ; jamais d'extrait privé dans la sortie."""
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'b82f1eba3bf8b8de102b0e1568978f085ef721ca'
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
    'dry_refuse': r'RuntimeError: Dry-activate refusé',
    'dry_incomplet': r'RuntimeError: Dry-activate absent ou incomplet',
    'interruption_socle': r'RuntimeError: Interruption du socle annoncée',
    'unite_etrangere': r'RuntimeError: Dry-activate annonce une unité étrangère',
    'permission_refusee': r'Permission denied',
    'systemd_indisponible': r'Failed to connect to (?:system|bus)|System has not been booted with systemd',
    'activation_script_refuse': r'activation script failed|failed to run activation script',
}


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
    if any(marqueurs.values()): raise ValueError('Diagnostic avant activation seulement')
    diagnostic = lire(DOSSIER/'diagnostic-prive.log'); dry = lire(DOSSIER/'dry-activate-prive.txt')
    construction.verifier_socle(candidat)
    print(json.dumps(dict(audit_amorcage=1, revision=REVISION, socle_conserve=True,
        activation=False, inscriptions=False, **classer(diagnostic,dry)), ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps(dict(audit_amorcage=1, diagnostic_refuse=True, activation=False)))
        raise SystemExit(1)
