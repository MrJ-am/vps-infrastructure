#!/usr/bin/env python3
"""Préparation sur le VPS uniquement : sauvegarde, construction et restauration isolée.

Aucune activation NixOS et aucune écriture SQL de production. Sources auditées
dans Actions 35349054287 ; une dérive exige une nouvelle revue.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys

OLD_SYSTEM = '/nix/store/5840x51nc7d2s7gw0zfyy6my47j6nh1i-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
NIXPKGS = '/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
APP_RELEASE = 'd8d0f17f37f030d58c152d5e57ca2e2c5b5814ea'
SOURCES = {
    'configuration.nix': '25b93411f479691ba9fbb394a6f24b028a29081e596f7815ef7dc936c53c7f09',
    'matheval.nix': '06b517d58429418e70146c7a763e8be4c47afb969e18a59fb639dc767e2d622b',
    'hostinger/configuration.nix': '5f800ae8e646ac5aca53c533a8425402e413c9adac79d07e50c93dc091b3b74b',
    'hostinger/hardware-configuration.nix': '530d087d26b68ff9ab6f79f4ab2334a25c56db92f5bf8978c53e12b7b7024455',
}
ACL_SQL = """
SELECT json_build_object(
 'database_owner', (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='matheval'),
 'database_acl', (SELECT json_agg(x ORDER BY grantee, privilege_type) FROM (
   SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
     pg_get_userbyid(a.grantor) AS grantor, a.privilege_type, a.is_grantable
   FROM pg_database d, LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a
   WHERE d.datname='matheval') x),
 'schema_owner', (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'),
 'schema_acl', (SELECT json_agg(x ORDER BY grantee, privilege_type) FROM (
   SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
     pg_get_userbyid(a.grantor) AS grantor, a.privilege_type, a.is_grantable
   FROM pg_namespace n, LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
   WHERE n.nspname='public') x),
 'role', (SELECT json_build_object('login',rolcanlogin,'superuser',rolsuper,
   'createdb',rolcreatedb,'createrole',rolcreaterole,'replication',rolreplication,
   'bypassrls',rolbypassrls,'inherit',rolinherit) FROM pg_roles WHERE rolname='matheval'));
"""
ROLE_SQL = 'ALTER ROLE matheval LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;'
ROLLBACK_SQL = ROLE_SQL + r"""
BEGIN;
ALTER DATABASE matheval OWNER TO matheval;
REVOKE ALL PRIVILEGES ON DATABASE matheval FROM PUBLIC;
REVOKE ALL PRIVILEGES ON DATABASE matheval FROM matheval;
GRANT ALL PRIVILEGES ON DATABASE matheval TO matheval;
GRANT CONNECT, TEMPORARY ON DATABASE matheval TO PUBLIC;
COMMIT;
\connect matheval
BEGIN;
ALTER SCHEMA public OWNER TO pg_database_owner;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM matheval;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO pg_database_owner;
COMMIT;
"""


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(*args, data=None, visible=False, stdout=None):
    result = subprocess.run([str(a) for a in args], input=data, text=data is None or isinstance(data, str),
                            stdout=stdout if stdout is not None else (None if visible else subprocess.PIPE),
                            stderr=None if visible else subprocess.PIPE)
    if result.returncode:
        if Path(str(args[0])).name in {'nix-instantiate', 'nix-build'} and result.stderr:
            print(result.stderr, file=sys.stderr)
        # Ne jamais afficher de contenu de dump ou de valeur applicative.
        raise RuntimeError(f'{Path(str(args[0])).name} : code {result.returncode}')
    return result.stdout


def sql(query, socket='/run/postgresql', database='matheval', user='postgres'):
    return run('runuser', '-u', user, '--', 'psql', '-XAt', '--set=ON_ERROR_STOP=1',
               '--host='+str(socket), '--dbname='+database, data=query).strip()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def acl(socket='/run/postgresql'):
    return json.loads(sql(ACL_SQL, socket))


def expected_acl():
    def grant(who, by, privilege):
        return dict(grantee=who, grantor=by, privilege_type=privilege, is_grantable=False)
    return dict(database_owner='matheval', schema_owner='pg_database_owner',
                database_acl=[grant(who, 'matheval', p) for who, rights in
                              [('PUBLIC', ['CONNECT', 'TEMPORARY']),
                               ('matheval', ['CONNECT', 'CREATE', 'TEMPORARY'])] for p in rights],
                schema_acl=[grant(who, 'pg_database_owner', p) for who, rights in
                            [('PUBLIC', ['USAGE']), ('pg_database_owner', ['CREATE', 'USAGE'])] for p in rights],
                role=dict(login=True, superuser=False, createdb=False, createrole=False,
                          replication=False, bypassrls=False, inherit=True))


def fingerprints(socket='/run/postgresql'):
    """Empreintes privées par ligne ; aucune réponse en clair dans les relevés."""
    tables = json.loads(sql("SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public';", socket))
    result = {}
    for table in tables:
        quoted = '"'+table.replace('"', '""')+'"'
        result[table] = sql(f'SELECT md5(row_to_json(t)::text) FROM public.{quoted} t ORDER BY 1;', socket).splitlines()
    return result


def tree_fingerprints(root):
    """Comparer le contenu généré, sans suivre de lien hors de /nix/store."""
    entries = {}
    def visit(path, relative):
        target = path.resolve()
        if not str(target).startswith('/nix/store/'):
            entries[relative] = 'external:'+str(target)
        elif path.is_dir():
            for child in sorted(path.iterdir()):
                visit(child, relative+'/'+child.name if relative else child.name)
        elif path.is_file():
            entries[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            entries[relative] = 'link:'+str(target)
    visit(Path(root), '')
    return entries


def check_original():
    require(str(Path('/run/current-system').resolve()) == OLD_SYSTEM, 'Génération active différente de l’audit')
    require(str(Path('/nix/var/nix/profiles/system').resolve()) == OLD_SYSTEM, 'Génération de démarrage différente')
    require(run('nix-instantiate', '--find-file', 'nixpkgs').strip() == NIXPKGS, 'Nixpkgs a changé')
    require(Path('/srv/matheval/current/RELEASE').read_text().strip() == APP_RELEASE, 'Publication applicative différente')
    for name, expected in SOURCES.items():
        require(hashlib.sha256((Path('/etc/nixos')/name).read_bytes()).hexdigest() == expected, 'Source NixOS modifiée : '+name)
    require(acl() == expected_acl(), 'Droits SQL différents de l’audit ; retour ciblé à revoir')
    require(sql("SELECT string_agg(datname,',' ORDER BY datname) FROM pg_database WHERE NOT datistemplate;") == 'matheval,postgres', 'Base supplémentaire à intégrer')
    require(sql("SELECT string_agg(rolname,',' ORDER BY rolname) FROM pg_roles WHERE rolname !~ '^pg_';") == 'matheval,postgres', 'Rôle supplémentaire à auditer')
    require(sql("SELECT count(*) FROM pg_stat_activity WHERE usename IS NOT NULL AND NOT (usename='postgres' OR (usename='matheval' AND datname='matheval' AND client_addr IS NULL));") == '0', 'Client SQL inattendu')


def prepare(commit):
    require(os.geteuid() == 0, 'Exécution root sur le VPS requise')
    require(re.fullmatch('[0-9a-f]{40}', commit), 'Commit invalide')
    os.umask(0o077)
    state = Path('/root/vps-migrations')/commit
    source = state/'source'
    require(source.is_dir(), 'Source absente')
    require(not (state/'prepared.json').exists(), 'Préparation déjà terminée')
    check_original()
    save(state/'acl-before.json', acl())
    (state/'rollback-acl.sql').write_text(ROLLBACK_SQL)
    run('tar', '--acls', '--xattrs', '-cpf', state/'etc-nixos-before.tar', '-C', '/etc', 'nixos')
    run('cp', '-a', '--no-dereference', '/etc/nixos/configuration.nix', state/'configuration.nix.before')
    installed = Path('/etc/nixos/vps-infrastructure')/commit
    require(not installed.exists(), 'Chemin candidat déjà présent')
    shutil.copytree(source, installed)
    run('sh', installed/'scripts/check.sh', visible=True)
    def evaluate(configuration):
        return json.loads(run('nix-instantiate', '--eval', '--strict', '--json',
                              installed/'scripts/migration-config.nix', '--argstr', 'configuration', configuration,
                              '-I', 'nixpkgs='+NIXPKGS))
    before = evaluate('/etc/nixos/configuration.nix')
    after = evaluate(str(installed/'hosts/hostinger/configuration.nix'))
    save(state/'config-before.json', before)
    save(state/'config-candidate.json', after)
    require(before['toplevel'] == OLD_SYSTEM, 'Les sources ne reconstruisent pas la génération auditée')
    require(before['invariant'] == after['invariant'], 'Un invariant système/application a changé')
    print('Sources et invariants validés ; construction du candidat.', flush=True)
    run('nix-build', '<nixpkgs/nixos>', '-A', 'system', '-I', 'nixpkgs='+NIXPKGS,
        '-I', 'nixos-config='+str(installed/'hosts/hostinger/configuration.nix'),
        '--out-link', state/'result', visible=True)
    candidate = str((state/'result').resolve())
    require(candidate == after['toplevel'], 'Construction différente de l’évaluation')
    roots = Path('/nix/var/nix/gcroots/vps-migrations')/commit
    roots.mkdir(parents=True, exist_ok=True)
    for name, target in [('previous', OLD_SYSTEM), ('candidate', candidate), ('nixpkgs', NIXPKGS),
                         ('python', str(Path(sys.executable).resolve().parent.parent))]:
        (roots/name).symlink_to(target)
    old_etc, new_etc = tree_fingerprints(Path(OLD_SYSTEM)/'etc'), tree_fingerprints(Path(candidate)/'etc')
    changes = sorted(k for k in old_etc.keys() | new_etc.keys() if old_etc.get(k) != new_etc.get(k))
    save(state/'etc-changes.json', changes)
    print('Fichiers générés modifiés : '+json.dumps(changes), flush=True)
    # Toute autre différence est examinée avant de permettre l’activation.
    allowed = {'systemd/system/matheval.service', 'systemd/system/postgresql.service',
               'systemd/system/postgresql-setup.service'}
    require(set(changes) <= allowed, 'Différences supplémentaires à revoir avant activation')
    for name in ['kernel', 'initrd', 'kernel-modules']:
        require((Path(OLD_SYSTEM)/name).resolve() == (Path(candidate)/name).resolve(), 'Élément de démarrage modifié : '+name)
    require(before['nginx'] == after['nginx'], 'Configuration ou binaire Nginx modifié')
    command = shlex.split(after['nginx']['command'])
    require(command[0] == after['nginx']['binary'] and '-c' in command, 'Commande Nginx inattendue')
    run(command[0], '-t', '-c', command[command.index('-c')+1], visible=True)
    dry = run(Path(candidate)/'bin/switch-to-configuration', 'dry-activate')
    (state/'dry-activate.txt').write_text(dry)
    print(dry, flush=True)
    permissions = json.loads(run('nix-instantiate', '--eval', '--strict', '--json', '--expr',
        '(import '+str(installed/'lib/databases.nix')+' (builtins.fromJSON (builtins.readFile '+str(installed/'databases.json')+'))).permissionsSQL'))
    (state/'candidate-acl.sql').write_text(ROLE_SQL+'\n'+permissions)
    dump = state/'matheval-before.dump'
    with dump.open('wb') as output:
        run('runuser', '-u', 'postgres', '--', 'pg_dump', '--host=/run/postgresql', '--create', '--format=custom', 'matheval', stdout=output)
    require(dump.stat().st_size > 0, 'Sauvegarde vide')
    # Cluster séparé, sans TCP ; les données de test restent privées au VPS.
    pg_bin = Path(before['invariant']['postgresqlPackage'])/'bin'
    isolated = Path('/var/lib/postgresql')/('vps-migration-check-'+commit)
    isolated.mkdir(mode=0o700)
    postgres = pwd.getpwnam('postgres')
    os.chown(isolated, postgres.pw_uid, postgres.pw_gid)
    isolated_dump = isolated/'before.dump'
    shutil.copy2(dump, isolated_dump)
    os.chown(isolated_dump, postgres.pw_uid, postgres.pw_gid)
    started = False
    try:
        run('runuser', '-u', 'postgres', '--', pg_bin/'initdb', '-D', isolated/'data', '--auth-local=trust', '--auth-host=reject', '--no-locale')
        run('runuser', '-u', 'postgres', '--', pg_bin/'pg_ctl', '-D', isolated/'data', '-l', isolated/'server.log', '-w',
            '-o', "-c listen_addresses='' -c unix_socket_directories="+str(isolated), 'start')
        started = True
        sql('CREATE ROLE matheval LOGIN;', isolated, 'postgres')
        run('runuser', '-u', 'postgres', '--', pg_bin/'pg_restore', '--host='+str(isolated), '--dbname=postgres', '--create', '--exit-on-error', isolated_dump)
        require(acl(isolated) == expected_acl(), 'Les droits de la restauration initiale diffèrent')
        rows = fingerprints(isolated)
        save(state/'rows-before.json', rows)
        sql(ROLE_SQL+'\n'+permissions, isolated, 'postgres')
        require(acl(isolated) != expected_acl(), 'Le test n’a pas appliqué les nouveaux droits')
        sql(ROLLBACK_SQL, isolated, 'postgres')
        require(acl(isolated) == expected_acl(), 'Le retour des droits n’est pas fidèle')
        sql(ROLLBACK_SQL, isolated, 'postgres')
        require(acl(isolated) == expected_acl(), 'Le retour des droits n’est pas réapplicable')
        require(fingerprints(isolated) == rows, 'Données de restauration modifiées')
    finally:
        if started:
            run('runuser', '-u', 'postgres', '--', pg_bin/'pg_ctl', '-D', isolated/'data', '-m', 'fast', '-w', 'stop')
        shutil.rmtree(isolated)
    encrypted = state/'matheval-before.dump.age'
    with encrypted.open('wb') as output:
        run(str(Path(shutil.which('matheval-backup')).resolve()), stdout=output)
    with encrypted.open('rb') as incoming:
        require(incoming.read(22) == b'age-encryption.org/v1\n', 'Export non reconnu comme chiffré age')
    check_original()
    report = dict(commit=commit, old_system=OLD_SYSTEM, old_boot=OLD_SYSTEM, candidate=candidate,
                  nixpkgs=NIXPKGS, installed=str(installed), python=str(Path(sys.executable).resolve()),
                  app_release=APP_RELEASE, changes=changes, restore_test=True, sql_rollback_test=True)
    save(state/'prepared.json', report)
    print('PRÉPARATION VALIDÉE : '+json.dumps(report), flush=True)


if __name__ == '__main__':
    prepare(sys.argv[1])
