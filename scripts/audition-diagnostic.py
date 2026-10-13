"""Constat Audition fermé, en lecture seule, sans traces ni identités privées."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


UNITES = ('sshd', 'mrj-auth', 'keycloak', 'vision-embeddings', 'phpfpm-nextcloud',
          'redis-nextcloud', 'nextcloud-backup.timer', 'postgresqlBackup-vision.timer',
          'postgresqlBackup-matheval.timer', 'kanidm', 'postgresql', 'mrjam-metier', 'nginx')


def commande(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def main(revision):
    if os.geteuid() != 0 or not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Cible refusée')
    d = Path('/root/mrjam-corrections/audition') / revision
    if not d.is_dir() or d.is_symlink(): raise ValueError('Candidat absent')
    resultat = {'format': 1, 'revision_sources': revision, 'lecture_seule': True,
                'generation': str(Path('/run/current-system').resolve()),
                'generation_demarrage': str(Path('/nix/var/nix/profiles/system').resolve()),
                'preparation': (d / 'preparation-audition.json').is_file(),
                'activation_engagee': (d / 'plan.json').is_file(),
                'terminee': (d / 'termine.json').is_file(), 'retour': (d / 'retour.json').is_file(),
                'certificat_audition_present': Path('/var/lib/acme/audition.mrj.am/fullchain.pem').is_file()}
    plan = json.loads((d / 'plan.json').read_text()) if resultat['activation_engagee'] else {}
    services = {}
    for n in UNITES:
        valeurs = dict(l.split('=', 1) for l in commande(['systemctl', 'show', n,
            '-p', 'MainPID', '-p', 'ActiveState']).splitlines())
        services[n] = {'etat': valeurs['ActiveState'],
                       'pid_change_depuis_plan': n in plan.get('pids', {}) and valeurs.get('MainPID', '') != plan['pids'][n]}
        if n == 'mrjam-metier' and valeurs['MainPID'] != '0':
            resultat['binaire_actif_sha256'] = hashlib.sha256((Path('/proc') / valeurs['MainPID'] / 'exe').read_bytes()).hexdigest()
    resultat['services'] = services
    evaluation = d / 'evaluation-audition.json'
    if evaluation.is_file():
        e = json.loads(evaluation.read_text())
        resultat['configuration_invariants'] = e['invariants']
        resultat['configuration_differences'] = e['differences']
    present = commande(['runuser', '-u', 'postgres', '--', 'psql', '-XAtq', '-d', 'vision',
                        '-c', "SELECT to_regnamespace('audition') IS NOT NULL"])
    resultat['schema_audition_present'] = present == 't'
    if present == 't':
        resultat['audition'] = json.loads(commande(['runuser', '-u', 'postgres', '--', 'psql', '-XAtq', '-d', 'vision',
            '-c', "BEGIN READ ONLY; SELECT json_build_object('version',(SELECT min(version) FROM audition.schema_migrations),"
            "'administrateurs_actifs',(SELECT count(*) FROM audition.administrateurs WHERE actif),"
            "'groupes',(SELECT count(*) FROM audition.groupes),'objets',(SELECT count(*) FROM audition.objets),"
            "'audit',(SELECT count(*) FROM audition.audit)); COMMIT;"]))
    # Evénements systemd uniquement, jamais MESSAGE ni sortie libre de processus.
    args = ['journalctl', '--since', '2 hours ago', '--no-pager', '-o', 'json', '-n', '500']
    for n in ('postgresql', 'kanidm', 'sshd', 'phpfpm-nextcloud', 'redis-nextcloud', 'vision-embeddings'):
        args += ['-u', n]
    evenements = []
    for l in commande(args).splitlines():
        try: e = json.loads(l)
        except ValueError: continue
        if e.get('UNIT') not in {n + '.service' for n in UNITES}: continue
        mid = e.get('MESSAGE_ID')
        # Identifiants publics : starting, started, stopping, stopped, reloading, reloaded, failed.
        if mid not in ('7d4958e842da4a758f6c1cdc7b36dcc5', '39f53479d3a045ac8e11786248231fbf',
                       'de5b426a63be47a7b6ac3eaac82e2f6f', '9d1aaa27d60140bd96365438aad20286',
                       'd34d037fff1847e6ae669a370e694725', '7b05ebc668384222baa8881179cfda54',
                       'be02cf6855d2428ba40df7e9d022f03d'): continue
        evenements.append({'unite': e['UNIT'], 'evenement': mid, 'utc_microsecondes': e.get('__REALTIME_TIMESTAMP')})
    resultat['evenements_systemd'] = evenements[-60:]
    print(json.dumps(resultat, sort_keys=True))


if __name__ == '__main__':
    if len(sys.argv) != 2: raise ValueError('Commande refusée')
    main(sys.argv[1])
