"""Construire l'amorçage réservé, sans activation, SQL de production ou personne."""
import argparse
import base64
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'
REFUS_PRECEDENT = 'f27c4d1e1f0b731da9e16116d584293599ee10d4'
SOURCE_PRECEDENTE = '8b015d952d55292ebce4fcfe99e7338eebc9bfac3b7b20f615cb02daa13acd55'
DESTINATAIRE_DIAGNOSTIC = 'age1uwzjmva3gz905h8hdussadzh5a2hpj7zyy37d3eq4fk3pq7q6vtquul8ue'


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / fichier)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


composants = charger('composants_amorcage', 'vision-mrjam-composants-construire.py')
proprietaire = charger('proprietaire_amorcage', 'vision-proprietaire.py')
construction = composants.construction
exiger = construction.exiger
audit = charger('audit_construction_amorcage', 'vision-identite-amorcage-auditer.py')


def etape(nom):
    global ETAPE
    ETAPE = nom; print(json.dumps({'etape': nom}), flush=True)


def preuve_composants(rapport, preuve, candidat, paquet):
    cles = ('version', 'infrastructure', 'import_prive', 'vision', 'style', 'keycloak',
        'paquet', 'lot', 'sources', 'construction', 'sources_agpl', 'garde_activation',
        'unites_construites', 'imports_python', 'imports_sans_privilege',
        'generation_constructible', 'activation', 'inscriptions', 'identite_humaine')
    exiger(set(rapport) == set(cles) and all(rapport.get(k) == preuve[k] for k in cles),
           'Preuve réelle des composants différente ou incomplète')
    exiger(rapport['version'] == 1 and rapport['keycloak'] == '26.7.3' and
        rapport['vision'] == candidat['vision'] and rapport['style'] == candidat['style'] and
        rapport['paquet'] == paquet and rapport['unites_construites'] == 7 and rapport['imports_python'] == 6 and
        all(rapport[k] is True for k in ('construction', 'sources_agpl', 'garde_activation', 'imports_sans_privilege')) and
        all(rapport[k] is False for k in ('generation_constructible', 'activation', 'inscriptions', 'identite_humaine')),
        'Composants ou garde inattendus')


def verifier_resume(r, candidat, paquet):
    vrais = ('unites_conservees', 'hotes_conserves', 'postgres_production_conserve',
        'parefeu_conserve', 'cluster_independant')
    faux = ('postgres_tcp', 'inscriptions', 'mode_vision_oidc', 'preconditions_validees',
        'activation', 'identite_humaine')
    exiger(r['version'] == 1 and r['keycloak_version'] == '26.7.3' and r['paquet'] == paquet and
        r['systeme_actif'] == candidat['audit']['systeme'] and
        r['fournisseur_source'] == candidat['audit']['fournisseur'] and
        all(r[k] is True for k in vrais) and all(r[k] is False for k in faux),
        'Candidat d’amorçage différent ou non fermé')
    for k in ('systeme_actif', 'systeme_amorcage', 'paquet', 'postgres_paquet', 'unite_identite', 'unite_cluster'):
        construction.store(r[k])
    exiger(r['systeme_actif'] != r['systeme_amorcage'] and set(r['unites_essentielles']) ==
        {'sshd', 'postgresql', 'vision', 'matheval', 'mrj-auth'}, 'Comparaison des unités incomplète')
    for path in r['unites_essentielles'].values(): construction.store(path)


def inventorier(pg):
    comptes = proprietaire.identifiants_auth(Path('/var/lib/vision/auth/htpasswd'),
        uid=0, gid=grp.getgrnam('vision-auth').gr_gid)
    env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
    env['PGCONNECT_TIMEOUT'] = '5'
    p = subprocess.Popen(['runuser', '-u', 'postgres', '--', str(pg / 'psql'),
        '-XAtq', '-v', 'ON_ERROR_STOP=1', '-h', '/run/postgresql', '-U', 'postgres', '-d', 'vision'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    def q(texte):
        p.stdin.write(texte + ';\n'); p.stdin.flush()
        resultat = p.stdout.readline(65537)
        exiger(resultat.endswith('\n') and len(resultat) <= 65536, 'Inventaire privé interrompu')
        return resultat.strip()
    try:
        p.stdin.write("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;"
            "SET LOCAL statement_timeout='10s'; SET LOCAL lock_timeout='5s';\n")
        p.stdin.flush()
        rapport = proprietaire.inspecter(q, comptes)
        p.stdin.write('COMMIT;\n'); p.stdin.close()
        exiger(p.wait(timeout=15) == 0, 'Inventaire privé interrompu')
        return rapport
    finally:
        if not p.stdin.closed:
            try: p.stdin.close()
            except BrokenPipeError: pass
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        p.stdout.close()


def commande_nginx(resume):
    paquet=resume['nginx_paquet'];construction.store(paquet)
    args=shlex.split(resume['nginx_commande'])
    exiger(len(args)==3 and args[0]==paquet+'/bin/nginx' and args[1]=='-c' and
        re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-nginx\.conf',args[2]),
        'Commande Nginx native non qualifiée')
    return args[0],args[2]


def outil(resume, paquet, executable):
    return construction.store(resume[paquet]) + '/bin/' + executable


def classer_refus(texte):
    classes = ('FileNotFoundError', 'PermissionError', 'ConstructionRefusee',
        'ValueError', 'KeyError', 'TimeoutExpired')
    return dict(exceptions=sorted(c for c in classes if re.search(r'\b'+c+r'\b', texte)),
        nginx=audit.classer_nginx(texte), configurations=audit.references_nginx(texte))


def auditer_refus(candidat, paquet):
    d = Path('/root/vision-identite-amorcage-operations') / REFUS_PRECEDENT
    for p in (d.parent, d, d/'source', d/'source/scripts'):
        construction.dossier_prive(p)
    exiger(not (d/'amorcage.json').exists(), 'Ancienne préparation déjà qualifiée')
    source = audit.lire(d/'source/scripts/vision-identite-amorcage-preparer.py')
    exiger(hashlib.sha256(source.encode()).hexdigest() == SOURCE_PRECEDENTE,
        'Source du refus précédent différente')
    resume = json.loads(audit.lire(d/'evaluation-privee.json'))
    verifier_resume(resume, candidat, paquet)
    exiger(str((d/'generation-amorcage').resolve()) == resume['systeme_amorcage'],
        'Génération précédente non retenue')
    commande_nginx(resume)
    diagnostic = audit.lire(d/'diagnostic-prive.log')
    return dict(revision=REFUS_PRECEDENT, generation_retenue=True,
        commande_nginx_qualifiee=True,
        runuser_socle_present=os.access(Path(resume['systeme_actif'])/'sw/bin/runuser', os.X_OK),
        **classer_refus(diagnostic))


def chiffrer_diagnostic(texte, age):
    # Seulement le stderr du nginx -t fixe, jamais un journal HTTP.
    if not isinstance(texte, bytes) or not texte or len(texte) > 16384:
        return dict(disponible=False)
    try:
        r = subprocess.run([age, '-a', '-r', DESTINATAIRE_DIAGNOSTIC], input=texte,
            capture_output=True, timeout=10)
        if r.returncode or len(r.stdout) > 32768 or not r.stdout.startswith(
                b'-----BEGIN AGE ENCRYPTED FILE-----\n') or not r.stdout.endswith(
                b'-----END AGE ENCRYPTED FILE-----\n'):
            return dict(disponible=False)
        return dict(disponible=True, age_base64=base64.b64encode(r.stdout).decode('ascii'))
    except (OSError, subprocess.TimeoutExpired):
        return dict(disponible=False)


def verifier_nginx(resume):
    nginx, configuration = commande_nginx(resume)
    runuser = outil(resume, 'runuser_paquet', 'runuser')
    age = outil(resume, 'age_paquet', 'age')
    try:
        r = subprocess.run([runuser, '-u', 'nginx', '--', nginx, '-t', '-c', configuration],
            capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise construction.ConstructionRefusee('Lanceur ou délai du contrôle Nginx refusé') from None
    if r.returncode:
        construction.preparation.diagnostic_prive(b'\nTest Nginx prive :\n'+r.stderr)
        print(json.dumps({'nginx_native': 'refuse',
            'diagnostic': classer_refus(r.stderr.decode(errors='replace')),
            'diagnostic_chiffre': chiffrer_diagnostic(r.stderr, age)}), flush=True)
        raise construction.ConstructionRefusee('Configuration Nginx native refusée')


def preparer(revision, controler=False):
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision),
           'Exécution Actions root identifiée requise')
    os.umask(0o077)
    d = Path('/root/vision-identite-amorcage-operations') / revision
    construction.dossier_prive(d.parent); construction.dossier_prive(d)
    exiger(ROOT == d / 'source', 'Source opérateur différente')
    construction.preparation.DIAGNOSTIC = d / 'diagnostic-prive.log'
    candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
    etape('invariants_actifs'); configuration = construction.verifier_socle(candidat)
    if controler:
        print(json.dumps({'socle_inchange': True, 'activation': False, 'inscriptions': False})); return
    exiger(not (d / 'amorcage.json').exists(), 'Préparation déjà terminée')
    etape('preuves_privees')
    def public(nom): return json.loads((ROOT / 'operations' / nom).read_text())
    preuve = public('vision-mrjam-composants-qualification.json')
    build = public('vision-identite-construction.json')
    unix = public('vision-identite-unix-qualification.json')
    import_prive = public('vision-identite-import-qualification.json')
    etape('audit_refus_precedent')
    print(json.dumps({'refus_precedent': auditer_refus(candidat, build['paquet'])}), flush=True)
    construction.verifier_socle(candidat)
    rapport = composants.rapport_prive('vision-mrjam-composants-operations', preuve, 'composants.json')
    preuve_composants(rapport, preuve, candidat, build['paquet'])
    composants.initial.preuve_unix(composants.rapport_prive('vision-identite-unix-operations',
        unix, 'qualification.json'), unix, candidat, build)
    composants.preuve_import(composants.rapport_prive('vision-identite-import-operations',
        import_prive, 'import.json'), import_prive, candidat, unix, build)
    composants.initial.identite.preparer(ROOT / 'operations/identite/realm.json',
        composants.initial.DESTINATION, composants.initial.DESTINATION / 'proton-smtp.json', controler=True)
    etape('inventaire_historique')
    historique = inventorier(Path(configuration['postgres_paquet']) / 'bin')
    construction.preparation.sauver(d / 'proprietaire-prive.json', historique)
    etape('evaluation_amorcage')
    args = [ROOT / 'scripts/vision-identite-amorcage.nix',
        '--argstr', 'configuration', '/etc/nixos/configuration.nix',
        '--argstr', 'fournisseur', candidat['audit']['fournisseur'],
        '-I', 'nixpkgs=' + candidat['audit']['nixpkgs']]
    resume = json.loads(construction.commande('nix-instantiate', '--eval', '--strict', '--json',
        *args, '--attr', 'resume'))
    verifier_resume(resume, candidat, build['paquet'])
    for paquet in ('runuser_paquet', 'age_paquet', 'tar_paquet'):
        construction.store(resume[paquet])
    construction.preparation.sauver(d / 'evaluation-privee.json', resume)
    disponible = next(int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()
        if l.startswith('MemAvailable:'))
    exiger(disponible >= 3 * 1024 * 1024, 'Mémoire disponible insuffisante')
    etape('construction_generation_amorcage')
    generation = construction.commande('nix-build', *args, '--attr', 'generation',
        '--out-link', d / 'generation-amorcage', '--max-jobs', '1', '--cores', '2', timeout=1500).strip()
    exiger(generation == resume['systeme_amorcage'] and
        str((d / 'generation-amorcage').resolve()) == generation and
        os.access(Path(generation) / 'bin/switch-to-configuration', os.X_OK),
        'Génération construite différente ou incomplète')
    etape('configuration_nginx_native')
    verifier_nginx(resume)
    etape('invariants_finaux'); construction.verifier_socle(candidat)
    resultat = dict(version=1, infrastructure=revision, composants=preuve['infrastructure'],
        vision=candidat['vision'], style=candidat['style'], paquet=resume['paquet'],
        systeme_actif=resume['systeme_actif'], systeme_amorcage=generation,
        construction=True, configuration_nginx_native=True, unites_conservees=True, hotes_conserves=True,
        postgres_production_conserve=True, cluster_independant=True,
        **proprietaire.public(historique), mode_vision_oidc=False,
        preconditions_validees=False, identite_humaine=False, activation=False, inscriptions=False)
    construction.preparation.sauver(d / 'amorcage.json', resultat)
    print(json.dumps(resultat), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('revision'); p.add_argument('--controler', action='store_true'); a = p.parse_args()
    try: preparer(a.revision, a.controler)
    except Exception:
        try: construction.preparation.diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        print(json.dumps({'amorcage': 'interrompu', 'etape': ETAPE,
            'activation': False, 'donnees_affichees': False}), file=sys.stderr, flush=True)
        sys.exit(1)
