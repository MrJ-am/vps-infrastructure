#!/usr/bin/env python3
"""Sonde VPS fermée : metadata système et agrégats, aucune donnée privée ni mutation.

Exécuter par le mécanisme administratif CI existant. Aucune commande, identité
ou requête SQL fournie par le demandeur n'est acceptée.
"""
import json
from pathlib import Path
import os
import subprocess
import time
import urllib.request
import urllib.error

SERVICES = ('vision', 'matheval', 'mrj-auth', 'vision-gestion', 'vision-cycle',
            'mrjam-admission', 'mrjam-fermeture', 'mrjam-courriel', 'keycloak',
            'nginx', 'postgresql', 'vision-embeddings', 'phpfpm-nextcloud')


def commande(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def sql(base, requete):
    # Entrée standard, pas de contenus/secrets dans argv ou journal.
    return json.loads(subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-XAtq',
                      '--set=ON_ERROR_STOP=1', '--dbname=' + base], input=requete,
                      check=True, capture_output=True, text=True, timeout=30).stdout)


def memoire(service):
    props = dict(line.split('=', 1) for line in commande(['systemctl', 'show', service,
                 '-p', 'MainPID', '-p', 'ControlGroup', '-p', 'ActiveState', '-p', 'MemoryMax']).splitlines())
    pid = int(props['MainPID'])
    groupe = Path('/sys/fs/cgroup') / props['ControlGroup'].lstrip('/') if props['ControlGroup'] else None
    rss = None
    if pid:
        statm = Path('/proc') / str(pid) / 'statm'
        if statm.exists():
            rss = int(statm.read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    return {'etat': props['ActiveState'], 'pid_present': pid > 0,
            'rss_processus_principal_octets': rss,
            'cgroup_octets_avec_cache': int((groupe / 'memory.current').read_text()) if groupe and (groupe / 'memory.current').exists() else None,
            'plafond_octets': props['MemoryMax']}


def latence(url, attentes):
    valeurs = []
    codes = []
    for _ in range(10):
        debut = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read(65536)  # réponses publiques uniquement, pas de journal du corps
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        codes.append(code)
        valeurs.append((time.monotonic() - debut) * 1000)
    if any(c not in attentes for c in codes):
        raise ValueError('Sonde publique hors contrat')
    valeurs.sort()
    return {'n': len(valeurs), 'codes': sorted(set(codes)), 'mediane_ms': round((valeurs[4] + valeurs[5]) / 2, 3),
            'p90_ms': round(valeurs[8], 3), 'type': 'GET public, dix lectures, sans authentification'}


def main():
    resultat = {'format': 1, 'mutation_metier': False,
                'generation': os.path.realpath('/run/current-system'),
                'generation_defaut': os.path.realpath('/nix/var/nix/profiles/system'),
                'nixpkgs': commande(['nix-instantiate', '--find-file', 'nixpkgs']),
                'services': {n: memoire(n) for n in SERVICES}}
    resultat['vision_comptes'] = sql('vision', """BEGIN READ ONLY;
SELECT json_build_object('total',count(*),'actifs',count(*) FILTER (WHERE actif),
 'administrateurs',count(*) FILTER (WHERE administrateur)) FROM vision_gestion.comptes;
COMMIT;""")
    resultat['vision_rattachements'] = sql('vision', """BEGIN READ ONLY;
SELECT json_build_object('identites', (SELECT count(*) FROM vision_gestion.identites),
 'identites_sans_compte',(SELECT count(*) FROM vision_gestion.identites i LEFT JOIN vision_gestion.comptes c USING(utilisateur) WHERE c.utilisateur IS NULL),
 'proprietaires_items',(SELECT count(DISTINCT utilisateur) FROM vision_items),
 'seances_ouvertes',(SELECT count(*) FROM vision_seances WHERE etat='ouverte'),
 'liens_croises',(SELECT count(*) FROM vision_liens l JOIN vision_items i ON i.id=l.item_id JOIN vision_fiches f ON f.id=l.fiche_id WHERE l.utilisateur<>i.utilisateur OR l.utilisateur<>f.utilisateur));
COMMIT;""")
    resultat['matheval'] = sql('matheval', """BEGIN READ ONLY;
SELECT json_build_object('administrateurs',(SELECT count(*) FROM administrators),
 'participations',(SELECT count(*) FROM participations),
 'participations_ouvertes',(SELECT count(*) FROM participations WHERE completed_at IS NULL),
 'corpus',(SELECT count(*) FROM corpus)); COMMIT;""")
    resultat['sql_roles'] = sql('postgres', """BEGIN READ ONLY;
SELECT coalesce(json_agg(json_build_object('role',rolname,'superuser',rolsuper,
 'bypassrls',rolbypassrls,'createrole',rolcreaterole,'createdb',rolcreatedb)), '[]'::json)
FROM pg_roles WHERE rolname IN ('vision','vision_migration','vision_identite',
 'vision_administration','vision_cycle','vision_admission','vision_fermeture','matheval');
COMMIT;""")
    closure = commande(['nix-store', '-qR', '/run/current-system']).splitlines()
    resultat['paquets_executables'] = [Path(p).name for p in closure if any(x in Path(p).name
                                     for x in ('-sbcl-', '-postgresql-', '-nodejs-', '-python3-', '-keycloak-', '-openjdk-', '-openssl-', '-sqlite-', '-age-'))]
    resultat['latences'] = {n: latence(url, codes) for n, url, codes in
       [('matheval_sante','https://principiipetit.io/matheval/api/health', (200,)),
        ('vision_vitrine','https://vision.mrj.am/', (200,)),
        ('mcp_refus','https://vision.mrj.am/mcp', (401,)),
        ('log_decouverte','https://log.mrj.am/realms/mrjam/.well-known/openid-configuration', (200,))]}
    resultat['limites'] = ['RSS principal distinct du cgroup qui inclut caches/enfants',
      'latences publiques depuis VPS sans charge hostile', 'aucune preuve de restauration nouvelle',
      'les agrégats ne remplacent pas les invariants privés avant bascule']
    print(json.dumps(resultat, sort_keys=True))


if __name__ == '__main__':
    main()
