"""Classer le seul journal privé du build Keycloak, en lecture seule.

La sortie ne contient que des catégories constantes et booléens. Aucun
stderr brut, extrait de source, URL ou nom arbitraire ne quitte la machine.
"""
import json
import os
from pathlib import Path
import re
import stat

REVISION = '226a928a58121b25a3c097c8d32b6843a05e19e6'
DOSSIER = Path('/root/vision-identite-operations') / REVISION
MOTIFS = {
    'hash_refuse': r'(?m)^error:.*hash mismatch in fixed-output derivation',
    'telechargement_refuse': r'(?m)^(?:error:.*unable to download|curl: \([0-9]+\))',
    'certificat_refuse': r'(?mi)^(?:error:|curl:).*?(?:SSL certificate|certificate verify|certificate verification)',
    'espace_disque_insuffisant': r'(?m)^.*(?:error:|No space left on device).*No space left on device',
    'permission_refusee': r'(?m)^(?:error:|[^\n]{1,200}:).*Permission denied',
    'nettoyage_spi_refuse': r"(?m)^\s*(?:>\s*)?rm: cannot remove '[^'\n]{1,300}/classes/META-INF/services/org\.keycloak\.[A-Za-z.]+': Permission denied",
    'groupe_nix_absent': r"(?m)^error: the group 'nixbld' specified in 'build-users-group' does not exist",
    'javac_absent': r'(?m)^.*javac: command not found',
    'symbole_java_absent': r'(?m)^.*error: cannot find symbol',
    'package_java_absent': r'(?m)^.*error: package [a-zA-Z0-9_.]+ does not exist',
    'version_java_incompatible': r'(?m)^.*(?:UnsupportedClassVersionError|class file has wrong version|invalid source release|release version [0-9]+ not supported)',
    'allocation_java_refusee': r'(?m)^.*(?:java.lang.OutOfMemoryError|Could not reserve enough space|Native memory allocation .* failed)',
    'quarkus_refuse': r'(?m)^.*(?:ERROR: Failed to run .build. command|Build failure: Build failed due to errors)',
    'patch_refuse': r'(?m)^.*(?:Hunk #[0-9]+ FAILED|patch does not apply)',
    'entree_nix_absente': r'(?m)^error:.*(?:path .* does not exist|getting status of .* No such file)',
    'assertion_nix_refusee': r'(?m)^error:.*assertion .* failed',
}
BUILDS = {
    'spi_mrjam': r'-mrjam-keycloak-26\.7\.3\.drv',
    'keycloak': r'^/nix/store/[0-9a-z]{32}-keycloak-26\.7\.3\.drv',
    'source': r'-source\.drv',
    'junixsocket': r'-(?:com_kohlschutter_junixsocket_)?junixsocket-[a-z-]+-[0-9.]+(?:\.jar)?\.drv',
    'systemd_notify': r'-(?:io_quarkiverse_systemd_notify_)?quarkus-systemd-notify(?:-deployment)?-[0-9.]+(?:\.jar)?\.drv',
}


def classer(contenu):
    refuses = re.findall(r"(?m)^error: (?:builder for|Cannot build) '(/nix/store/[0-9a-z]{32}-[^'\n]{1,160}\.drv)'", contenu)
    permissions = '\n'.join(l for l in contenu.splitlines() if 'Permission denied' in l)
    return {'categories': [nom for nom, motif in MOTIFS.items() if re.search(motif, contenu)],
        'builders_refuses': [nom for nom, motif in BUILDS.items() if
            any(re.search(motif + '$', p) for p in refuses)],
        'refus_nix': bool(re.search(r'(?m)^error:', contenu)),
        'permission_contexte': [nom for nom, motif in {
            'compilateur_mrjam': r'compiler\.sh',
            'source_java': r'/src/|\.java\b',
            'javac': r'\bjavac\b', 'java': r'\bjava\b', 'jar': r'\bjar\b',
            'find': r'\bfind:', 'cp': r'\bcp:', 'cd': r'\bcd:', 'mkdir': r'\bmkdir:', 'rm': r'\brm:',
            'mktemp': r'\bmktemp:', 'sh': r'(?:^|\s)sh:',
            'repertoire_root': r'/root/', 'repertoire_build': r'/build/',
            'repertoire_tmp': r'/tmp/', 'repertoire_store': r'/nix/store/',
            'librairies': r'/lib/|\.jar\b',
            'ressources_spi': r'/classes/META-INF/services/',
        }.items() if re.search(motif, permissions)]}


def lire(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Journal privé requis')
        if info.st_size > 262144: raise ValueError('Journal trop grand')
        return os.read(fd, 262144).decode('utf-8', errors='replace')
    finally:
        os.close(fd)


def main():
    if os.geteuid() != 0: raise ValueError('Audit Actions root requis')
    for path in (DOSSIER.parent, DOSSIER):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Dossier privé requis')
    resultat = dict(audit_construction=1, revision=REVISION, activation=False,
        **classer(lire(DOSSIER / 'diagnostic-prive.log')))
    resultat['rapport_present'] = (DOSSIER / 'construction.json').is_file()
    print(json.dumps(resultat, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps(dict(audit_construction=1, diagnostic_refuse=True, activation=False)))
        raise SystemExit(1)
