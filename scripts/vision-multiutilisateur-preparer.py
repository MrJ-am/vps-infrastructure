"""Préparer depuis Actions : dump privé, migrations et retour ACL dans un cluster isolé.

Aucune activation NixOS, mutation SQL de production, création d'identité réelle
ou ouverture. Les données du dump ne quittent pas le VPS en clair. Un changement
de génération ou de release depuis l'audit bloque cette opération.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'
DIAGNOSTIC = None
ETAPES = frozenset(('demarrage', 'invariants_actifs', 'source_candidate',
    'evaluation_nixos', 'conservation_configuration', 'snapshot_postgresql',
    'releve_acl', 'empreintes_historiques', 'dump_transactionnel',
    'chiffrement_dump', 'creation_cluster_isole', 'restauration_isolee',
    'verification_socle', 'migrations_isolees', 'retour_droits',
    'invariants_finaux', 'rapport_final'))
spec = importlib.util.spec_from_file_location('vision_acl', ROOT / 'scripts/vision-acl.py')
acl = importlib.util.module_from_spec(spec); spec.loader.exec_module(acl)


class PreparationRefusee(RuntimeError):
    """Raison constante écrite par ce programme, jamais une réponse PostgreSQL."""


def exiger(condition, message):
    if not condition: raise PreparationRefusee(message)


def etape(nom):
    global ETAPE
    if nom not in ETAPES: raise ValueError('Étape inconnue')
    ETAPE = nom
    print(json.dumps({'etape': nom}, ensure_ascii=False), flush=True)


def diagnostic_prive(contenu):
    if DIAGNOSTIC is None: return
    fd = os.open(DIAGNOSTIC, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Diagnostic non privé')
        if info.st_size < 262144:
            with os.fdopen(fd, 'wb') as fichier:
                fd = None
                fichier.write(contenu[:65536]); fichier.flush(); os.fsync(fichier.fileno())
    finally:
        if fd is not None: os.close(fd)


def constater(revision):
    """Constat de présence uniquement ; aucun fichier de données n'est lu."""
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'Constat Actions root identifié requis')
    d = Path('/root/vision-multiutilisateur-operations') / revision
    fichiers = {'source_extraite': 'vision/scripts/roles.sql',
        'evaluation_conservee': 'systeme-actif.json', 'configuration_conservee': 'nixos-avant.tar',
        'acl_conservees': 'acl-avant.json', 'empreintes_conservees': 'empreintes-privees.json',
        'dump_prive_present': 'vision.dump', 'dump_chiffre_present': 'vision.dump.age',
        'retour_prepare': 'retour-acl.sql', 'preparation_terminee': 'preparation.json'}
    print(json.dumps({'constat_revision': revision,
        **{nom: (d / chemin).is_file() for nom, chemin in fichiers.items()}}, ensure_ascii=False))


def commande(*args, entree=None, env=None):
    r = subprocess.run([str(a) for a in args], input=entree, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env)
    if r.returncode:
        diagnostic_prive(b'\nCommande interrompue ; stderr prive :\n' + r.stderr)
        raise PreparationRefusee('Commande refusée : ' + Path(str(args[0])).name)
    return r.stdout


def sauver(path, contenu):
    with open(path, 'x') as f:
        json.dump(contenu, f, ensure_ascii=False, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())


def extraire(source, destination, empreinte, revision):
    exiger(hashlib.sha256(source.read_bytes()).hexdigest() == empreinte, 'Source candidate différente')
    with tarfile.open(source, 'r:gz') as archive:
        exiger(archive.pax_headers.get('comment') == revision, 'Révision Git de l’archive différente')
        membres = archive.getmembers()
        exiger(len(membres) < 10000 and sum(m.size for m in membres) < 50000000, 'Archive trop grande')
        for m in membres:
            exiger(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and
                (m.isfile() or m.isdir()), 'Archive non régulière')
        archive.extractall(destination, filter='data')


def sql(socket, base, texte):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
    return commande('runuser', '-u', 'postgres', '--', 'psql', '-XAtq', '-v', 'ON_ERROR_STOP=1',
        '-h', socket, '-d', base, '-U', 'postgres', '-f', '-',
        entree=("SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n" + texte).encode(), env=env).decode().strip()


def empreintes(socket, base, tables):
    return {t: sql(socket, base, 'SELECT md5(coalesce(string_agg(md5(to_jsonb(t)::text),\' \'' +
        ' ORDER BY md5(to_jsonb(t)::text)),\'\')) FROM public.' + acl.identifiant(t) + ' t;') for t in tables}


def preparer(revision):
    global DIAGNOSTIC
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'Exécution Actions root identifiée requise')
    os.umask(0o077)
    d = Path('/root/vision-multiutilisateur-operations') / revision
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    exiger(not d.is_symlink() and not d.stat().st_mode & 0o077 and
        d.stat().st_uid == os.geteuid(), 'Dossier opérateur non privé')
    DIAGNOSTIC = d / 'diagnostic-prive.log'
    candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
    audit = candidat['audit']
    def controler():
        exiger(str(Path('/run/current-system').resolve()) == audit['systeme'] and
            str(Path('/nix/var/nix/profiles/system').resolve()) == audit['systeme'], 'Génération différente : nouvel audit requis')
        exiger(str(Path('/srv/vision/current').resolve()) == audit['vision'], 'Release Vision différente : nouvel audit requis')
        exiger(commande('nix-instantiate', '--find-file', 'nixpkgs').decode().strip() == audit['nixpkgs'], 'Nixpkgs installé différent')
    etape('invariants_actifs'); controler()
    exiger(not (d / 'preparation.json').exists(), 'Préparation déjà terminée')
    etape('source_candidate')
    source = d / 'vision'; source.mkdir(mode=0o700)
    extraire(ROOT / 'vendor/vision-multiutilisateur-source.tar.gz', source, candidat['source_sha256'], candidat['vision'])
    exiger(json.loads((source / 'interface/style.lock.json').read_text())['revision'] == candidat['style'], 'Style différent')
    etape('evaluation_nixos')
    configuration = json.loads(commande('nix-instantiate', '--eval', '--strict', '--json',
        ROOT / 'scripts/vision-multiutilisateur-config.nix', '--argstr', 'configuration', '/etc/nixos/configuration.nix',
        '-I', 'nixpkgs=' + audit['nixpkgs']).decode())
    exiger(configuration['systeme'] == audit['systeme'] and configuration['postgres_majeure'] == '17' and
        configuration['postgres_tcp'] is False and configuration['postgres_ecoute'] == '', 'Socle actif non reproduit')
    sauver(d / 'systeme-actif.json', configuration)
    etape('conservation_configuration')
    commande('tar', '--acls', '--xattrs', '-cpf', d / 'nixos-avant.tar', '-C', '/etc', 'nixos')
    exiger(not (d / 'vision.dump').exists(), 'Dump déjà présent')
    # Transaction exportée : dump, droits et empreintes désignent la même copie,
    # même si la personne continue à utiliser la version active pendant le relevé.
    etape('snapshot_postgresql')
    pg = subprocess.Popen(['runuser', '-u', 'postgres', '--', 'psql', '-XAtq', '-v', 'ON_ERROR_STOP=1',
        '-h', '/run/postgresql', '-U', 'postgres', '-d', 'vision'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True)
    def requete(texte):
        pg.stdin.write(texte + ';\n'); pg.stdin.flush()
        ligne = pg.stdout.readline().strip(); exiger(bool(ligne), 'Transaction de relevé interrompue'); return ligne
    try:
        pg.stdin.write("SET TIME ZONE 'UTC'; SET DateStyle='ISO'; BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"); pg.stdin.flush()
        snapshot = requete('SELECT pg_export_snapshot()')
        exiger(re.fullmatch('[0-9A-F-]{1,64}', snapshot), 'Snapshot PostgreSQL invalide')
        etape('releve_acl')
        releve = acl.relever(requete); sauver(d / 'acl-avant.json', releve)
        etape('empreintes_historiques')
        tables = json.loads(requete("SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' AND tablename<>'vision_schema_migrations'"))
        avant = {t: requete('SELECT md5(coalesce(string_agg(md5(to_jsonb(t)::text),\' \'' +
            ' ORDER BY md5(to_jsonb(t)::text)),\'\')) FROM public.' + acl.identifiant(t) + ' t') for t in tables}
        sauver(d / 'empreintes-privees.json', avant)
        etape('dump_transactionnel')
        with open(d / 'vision.dump', 'xb') as f:
            r = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', '--snapshot=' + snapshot,
                '-h', '/run/postgresql', '-U', 'postgres', 'vision'], stdout=f, stderr=subprocess.DEVNULL)
            exiger(r.returncode == 0, 'Dump transactionnel refusé')
    finally:
        if pg.poll() is None:
            pg.stdin.write('ROLLBACK;\n'); pg.stdin.close(); pg.wait(timeout=20)
    # Une autre copie privée possède sa propre instance et ses propres rôles :
    # roles.sql n'est jamais exécuté dans le cluster de production.
    etape('chiffrement_dump')
    recipient = configuration['recipient_age']
    commande('age', '-r', recipient, '-o', d / 'vision.dump.age', d / 'vision.dump')
    etape('creation_cluster_isole')
    postgres = pwd.getpwnam('postgres')
    isole = Path('/var/lib/postgresql') / ('vision-qualification-' + revision[:12] + '-' + uuid.uuid4().hex[:6])
    isole.mkdir(mode=0o700); os.chown(isole, postgres.pw_uid, postgres.pw_gid)
    b = Path(configuration['postgres_paquet']) / 'bin'; actif = False
    dump = isole / 'vision.dump'; shutil.copyfile(d / 'vision.dump', dump); dump.chmod(0o600); os.chown(dump, postgres.pw_uid, postgres.pw_gid)
    (d / 'vision.dump').unlink()
    try:
        commande('runuser', '-u', 'postgres', '--', b / 'initdb', '-D', isole / 'data', '--auth-local=trust', '--auth-host=reject', '--no-locale')
        commande('runuser', '-u', 'postgres', '--', b / 'pg_ctl', '-D', isole / 'data', '-l', isole / 'serveur.log', '-w',
            '-o', "-c listen_addresses='' -c unix_socket_directories=" + str(isole), 'start'); actif = True
        etape('restauration_isolee')
        sql(str(isole), 'postgres', 'CREATE ROLE vision LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; CREATE DATABASE vision OWNER vision;')
        commande('runuser', '-u', 'postgres', '--', b / 'pg_restore', '--exit-on-error', '-h', isole, '-U', 'postgres', '-d', 'vision', dump)
        exiger(empreintes(str(isole), 'vision', tables) == avant, 'La copie restaurée diffère')
        # Refuser un nouveau socle ou une migration déjà partiellement active.
        etape('verification_socle')
        exiger(sql(str(isole), 'vision', 'SELECT count(*)=18 FROM vision_schema_migrations WHERE version BETWEEN 1 AND 18') == 't' and
            sql(str(isole), 'vision', 'SELECT count(*) FROM vision_schema_migrations WHERE version>18') == '0', 'Socle Vision inattendu')
        env = {**os.environ, 'PGHOST': str(isole), 'PGUSER': 'postgres', 'PGDATABASE': 'vision', 'PGPASSWORD': ''}
        etape('migrations_isolees')
        commande('sh', source / 'scripts/migrate.sh', env=env)
        sql(str(isole), 'vision', (source / 'scripts/roles.sql').read_text())
        exiger(empreintes(str(isole), 'vision', tables) == avant, 'Migrations : donnée historique modifiée')
        etape('retour_droits')
        retour = acl.retour(releve); (d / 'retour-acl.sql').write_text(retour)
        sql(str(isole), 'vision', retour)
        apres = acl.relever(lambda q: sql(str(isole), 'vision', q))
        # Les nouveaux objets restent présents ; comparer seulement les objets
        # historiques, leurs droits effectifs, owners et états RLS.
        historiques = {(o['type'], o['nom']) for o in releve['objets']}
        exiger([o for o in apres['objets'] if (o['type'], o['nom']) in historiques] == releve['objets'] and
            apres['role'] == releve['role'], 'Retour ACL/owners/RLS non fidèle')
        sql(str(isole), 'vision', retour)
        exiger(empreintes(str(isole), 'vision', tables) == avant, 'Retour : données modifiées')
    finally:
        if actif: commande('runuser', '-u', 'postgres', '--', b / 'pg_ctl', '-D', isole / 'data', '-m', 'fast', '-w', 'stop')
        shutil.rmtree(isole)
    etape('invariants_finaux'); controler()
    etape('rapport_final')
    rapport = dict(version=1, infrastructure=revision, vision=candidat['vision'], style=candidat['style'],
        restauration_vision_reelle=True, migrations_sans_perte=True, retour_acl_owners_rls=True,
        retour_rejouable=True, activation=False, inscriptions=False,
        keycloak_candidat=configuration['keycloak_version'],
        reste=['construction et qualification JDBC Unix', 'identité initiale et MFA', 'SMTP et registre externe',
            'contrats et clé de restauration', 'essai NixOS avec retour autonome'])
    sauver(d / 'preparation.json', rapport); print(json.dumps(rapport, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('revision')
    p.add_argument('--constater', action='store_true'); a = p.parse_args()
    try:
        if a.constater: constater(a.revision)
        else: preparer(a.revision)
    except Exception as erreur:
        try: diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        rapport = {'preparation': 'interrompue', 'etape': ETAPE,
            'activation': False, 'donnees_affichees': False}
        if isinstance(erreur, PreparationRefusee): rapport['raison'] = str(erreur)
        print(json.dumps(rapport, ensure_ascii=False), file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__': main()
