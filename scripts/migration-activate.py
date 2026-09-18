#!/usr/bin/env python3
"""Bascule du candidat préparé, protégée par un retour systemd indépendant."""
from collections import Counter
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import time


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rows_preserved(before, after):
    return all(name in after and not (Counter(rows) - Counter(after[name]))
               for name, rows in before.items())


def commit_allowed(state):
    return ((state/'tested').exists() and not any((state/name).exists()
            for name in ['rollback-started', 'rolled-back', 'worker-failed', 'committed']))


class Migration:
    def __init__(self, prepared_commit, operation_commit):
        require(re.fullmatch('[0-9a-f]{40}', prepared_commit), 'Commit préparé invalide')
        require(re.fullmatch('[0-9a-f]{40}', operation_commit), 'Commit opérateur invalide')
        require(os.geteuid() == 0, 'Exécution root sur le VPS requise')
        os.umask(0o077)
        self.state = Path('/root/vps-migrations')/prepared_commit
        self.prepared = json.loads((self.state/'prepared.json').read_text())
        require(self.prepared['commit'] == prepared_commit, 'Préparation incohérente')
        require(self.prepared['restore_test'] and self.prepared['sql_rollback_test'], 'Préparation incomplète')
        self.operation = operation_commit
        self.short = prepared_commit[:12]
        self.worker_unit = 'vps-test-'+self.short
        self.rollback_unit = 'vps-rollback-'+self.short
        spec = importlib.util.spec_from_file_location('migration_prepare', self.state/'source/scripts/migration-prepare.py')
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        self.run, self.sql = self.helper.run, self.helper.sql
        self.config = json.loads((self.state/'config-candidate.json').read_text())
        self.pg_bin = Path(self.config['invariant']['postgresqlPackage'])/'bin'
        self.runtime_path = self.prepared['old_system']+'/sw/bin:/run/wrappers/bin'
        self.service_environment = ['--setenv=PATH='+self.runtime_path,
                                    '--setenv=NIX_PATH=nixpkgs='+self.prepared['nixpkgs']]

    def rollback_script(self):
        # Script autonome, outils de l’ancienne génération, aucune dépendance au
        # code applicatif/candidat, aucune reconstruction ni restauration de données.
        q = shlex.quote
        # Conserver argv[0] : certains outils NixOS sont des liens vers un
        # exécutable multicall (coreutils). Résoudre le dernier lien change
        # leur commande. Le profil de l’ancienne génération est déjà figé.
        binaries = {name: self.prepared['old_system']+'/sw/bin/'+name for name in
                    ['bash', 'flock', 'cp', 'mv', 'systemctl', 'nix-env', 'runuser', 'psql', 'touch', 'readlink']}
        state, old, boot = str(self.state), self.prepared['old_system'], self.prepared['old_boot']
        script = f'''#!{binaries['bash']}
set -euo pipefail
export PATH={q(self.runtime_path)}
exec 9>{q(state+'/finalize.lock')}
{q(binaries['flock'])} 9
test ! -e {q(state+'/committed')} || exit 0
{q(binaries['touch'])} {q(state+'/rollback-started')}
{q(binaries['systemctl'])} stop {q(self.worker_unit+'.service')} || true
{q(binaries['cp'])} -a --no-dereference {q(state+'/configuration.nix.before')} {q('/etc/nixos/.configuration.nix.rollback-'+self.short)}
{q(binaries['mv'])} -Tf {q('/etc/nixos/.configuration.nix.rollback-'+self.short)} /etc/nixos/configuration.nix
{q(binaries['nix-env'])} --profile /nix/var/nix/profiles/system --set {q(boot)}
{q(boot+'/bin/switch-to-configuration')} boot
{q(old+'/bin/switch-to-configuration')} test
{q(binaries['runuser'])} -u postgres -- {q(binaries['psql'])} -Xq --set=ON_ERROR_STOP=1 --host=/run/postgresql --dbname=postgres --file=- < {q(state+'/rollback-acl.sql')}
{q(binaries['systemctl'])} is-active sshd nginx postgresql matheval
test "$({q(binaries['readlink'])} -f /run/current-system)" = {q(old)}
test "$({q(binaries['readlink'])} -f /nix/var/nix/profiles/system)" = {q(boot)}
{q(binaries['touch'])} {q(state+'/rolled-back')}
{q(binaries['systemctl'])} stop {q(self.rollback_unit+'.timer')} || true
echo 'Ancienne génération, entrée NixOS et droits SQL rétablis ; données conservées.'
'''
        path = self.state/'rollback.sh'
        path.write_text(script)
        path.chmod(0o700)
        self.run(binaries['bash'], '-n', path)

    def plan(self):
        self.helper.check_original()
        require(not (self.state/'started').exists(), 'Une activation a déjà été engagée')
        require(str((self.state/'result').resolve()) == self.prepared['candidate'], 'Candidat différent')
        result = subprocess.run([self.prepared['candidate']+'/bin/switch-to-configuration', 'dry-activate'],
                                capture_output=True, text=True, check=True)
        dry = result.stdout+'\n'+result.stderr
        (self.state/'dry-activate-reviewed.txt').write_text(dry)
        print(dry, flush=True)
        # Les seules unités modifiées dans la génération sont les trois unités
        # déjà comparées. Tout effet sur un service réseau impose un arrêt.
        require(not re.search(r'(?:stop|restart)[^\n]*(?:sshd|nginx|networkd|resolved)', dry, re.I),
                'Le dry-run annonce une interruption du réseau/SSH/Nginx')
        self.rollback_script()
        # Exécuter les vrais contrôles en lecture seule dans le même contexte
        # systemd que l’essai : ce service n’hérite pas du profil de connexion SSH.
        self.run('systemd-run', '--unit=vps-preflight-'+self.operation[:12], '--wait', '--pipe', '--collect',
                 '--property=Type=oneshot', *self.service_environment,
                 self.prepared['python'], str(Path(__file__)), 'preflight',
                 self.prepared['commit'], self.operation, visible=True)
        rehearsal = self.state/'rehearsal-fired'
        if rehearsal.exists():
            rehearsal.unlink()
        self.run('systemd-run', '--unit=vps-rehearsal-'+self.operation[:12], '--on-active=5s',
                 '--timer-property=AccuracySec=1s', '--collect',
                 self.prepared['old_system']+'/sw/bin/touch', rehearsal)
        self.helper.save(self.state/'plan.json', dict(operation=self.operation, candidate=self.prepared['candidate'],
                                                    program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                                    rollback_script_checked=True, time=time.time()))
        print('Plan et retour arrière préparés ; aucune activation.', flush=True)

    def start(self):
        self.helper.check_original()
        require((self.state/'rehearsal-fired').exists(), 'Timer indépendant non vérifié')
        require((self.state/'plan.json').exists(), 'Plan absent')
        require(json.loads((self.state/'plan.json').read_text())['program_sha256'] ==
                hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'Le programme a changé depuis le plan')
        require(not (self.state/'started').exists(), 'Activation déjà engagée')
        # Le programme de commande est copié hors de la configuration candidate.
        control_python = self.state/'activation.py'
        shutil.copy2(Path(__file__), control_python)
        control = self.state/'control'
        control.write_text('#!'+str(Path(shutil.which('bash')).resolve())+'\nexec '+
                           shlex.quote(self.prepared['python'])+' '+shlex.quote(str(control_python))+
                           ' "$@" '+shlex.quote(self.prepared['commit'])+' '+shlex.quote(self.operation)+'\n')
        control.chmod(0o700)
        self.rollback_script()
        (self.state/'started').touch()
        self.helper.save(self.state/'activation.json', dict(operation=self.operation, started=time.time()))
        self.run('systemd-run', '--unit='+self.rollback_unit, '--on-active=15min',
                 '--timer-property=AccuracySec=1s', '--property=Type=oneshot',
                 '--property=TimeoutStartSec=5min', str(self.state/'rollback.sh'))
        self.run('systemctl', 'is-active', self.rollback_unit+'.timer')
        self.run('systemd-run', '--unit='+self.worker_unit, '--property=Type=exec',
                 '--property=TimeoutStopSec=30s', '--setenv=PATH='+self.runtime_path,
                 '--setenv=NIX_PATH=nixpkgs='+self.prepared['nixpkgs'],
                 str(control), 'worker')
        print('Retour automatique armé pour 15 minutes ; essai lancé.', flush=True)

    def verify_local(self):
        require(not (self.state/'rollback-started').exists(), 'Retour arrière commencé')
        require(str(Path('/run/current-system').resolve()) == self.prepared['candidate'], 'Le candidat n’est plus actif')
        self.run('systemctl', 'is-active', 'sshd', 'nginx', 'postgresql', 'matheval', 'postgresql-setup')
        require(self.run('systemctl', 'show', 'postgresql-setup', '--property=Result', '--value').strip() == 'success', 'Échec du provisionnement SQL')
        require(self.sql('SHOW server_version;') == '17.11', 'Version PostgreSQL modifiée')
        require(self.sql('SHOW data_directory;') == '/var/lib/postgresql/17', 'Répertoire PostgreSQL modifié')
        require(self.sql('SHOW listen_addresses;') == '', 'PostgreSQL écoute en TCP')
        require(self.sql('SHOW unix_socket_directories;') == '/run/postgresql', 'Socket modifié')
        require(self.sql('SELECT current_user;', user='matheval') == 'matheval', 'Connexion applicative impossible')
        denied = subprocess.run(['runuser', '-u', 'matheval', '--', 'psql', '-XAt', '--host=/run/postgresql',
                                 '--dbname=postgres', '-c', 'SELECT 1;'], capture_output=True, text=True)
        require(denied.returncode != 0 and 'reject' in denied.stderr.lower(), 'Isolation des bases non effective')
        require(self.sql('SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;') == '0', 'HBA invalide')
        rights = self.helper.acl()
        require(rights['role'] == self.helper.expected_acl()['role'], 'Privilèges du rôle modifiés')
        require(rights['database_owner'] == 'matheval' and rights['schema_owner'] == 'pg_database_owner', 'Propriétaire SQL modifié')
        require(all(x['grantee'] != 'PUBLIC' for x in rights['database_acl']+rights['schema_acl']), 'Droits PUBLIC encore présents')
        before = json.loads((self.state/'rows-at-switch.json').read_text())
        require(rows_preserved(before, self.helper.fingerprints()), 'Une ligne antérieure a disparu ou changé')
        identity = json.loads((self.state/'database-identity.json').read_text())
        stat = Path('/var/lib/postgresql/17').stat()
        require(identity == [stat.st_dev, stat.st_ino, self.sql("SELECT oid FROM pg_database WHERE datname='matheval';")], 'Identité du stockage modifiée')
        require(Path('/srv/matheval/current/RELEASE').read_text().strip() == self.prepared['app_release'], 'Publication applicative modifiée')
        health = json.loads(self.run('curl', '--fail', '--silent', '--show-error', '--max-time', '10',
                                     'http://127.0.0.1:3000/matheval/api/health'))
        require(health.get('status') == 'ok', 'API non saine')
        command = shlex.split(self.config['nginx']['command'])
        self.run(command[0], '-t', '-c', command[command.index('-c')+1])
        self.run('systemctl', 'is-active', 'postgresqlBackup-matheval.timer',
                 'acme-renew-principiipetit.io.timer', 'acme-renew-www.principiipetit.io.timer')

    def verify_backups(self):
        begun = time.time()
        self.run('systemctl', 'start', 'postgresqlBackup-matheval.service')
        require(self.run('systemctl', 'show', 'postgresqlBackup-matheval', '--property=Result', '--value').strip() == 'success', 'Sauvegarde locale en échec')
        dump = Path('/var/backup/postgresql/matheval.sql.gz')
        require(dump.is_file() and dump.stat().st_mtime >= begun-2 and dump.stat().st_size > 0, 'Sauvegarde locale non renouvelée')
        isolated = Path('/var/lib/postgresql')/('vps-after-check-'+self.prepared['commit'])
        isolated.mkdir(mode=0o700)
        pguser = pwd.getpwnam('postgres')
        os.chown(isolated, pguser.pw_uid, pguser.pw_gid)
        restored_sql = isolated/'backup.sql'
        with gzip.open(dump, 'rb') as source, restored_sql.open('wb') as out:
            shutil.copyfileobj(source, out)
        os.chown(restored_sql, pguser.pw_uid, pguser.pw_gid)
        started = False
        try:
            self.run('runuser', '-u', 'postgres', '--', self.pg_bin/'initdb', '-D', isolated/'data', '--auth-local=trust', '--auth-host=reject', '--no-locale')
            self.run('runuser', '-u', 'postgres', '--', self.pg_bin/'pg_ctl', '-D', isolated/'data', '-l', isolated/'server.log', '-w',
                     '-o', "-c listen_addresses='' -c unix_socket_directories="+str(isolated), 'start')
            started = True
            self.sql('CREATE ROLE matheval LOGIN;', isolated, 'postgres')
            self.run('runuser', '-u', 'postgres', '--', self.pg_bin/'psql', '-Xq', '--set=ON_ERROR_STOP=1',
                     '--host='+str(isolated), '--dbname=postgres', '--file='+str(restored_sql))
            require(rows_preserved(json.loads((self.state/'rows-at-switch.json').read_text()),
                                   self.helper.fingerprints(isolated)), 'Restauration locale incomplète')
        finally:
            if started:
                self.run('runuser', '-u', 'postgres', '--', self.pg_bin/'pg_ctl', '-D', isolated/'data', '-m', 'fast', '-w', 'stop')
            shutil.rmtree(isolated)
        encrypted = self.state/'matheval-after.dump.age'
        with encrypted.open('wb') as output:
            self.run(str(Path(shutil.which('matheval-backup')).resolve()), stdout=output)
        with encrypted.open('rb') as source:
            require(source.read(22) == b'age-encryption.org/v1\n', 'Export chiffré invalide')
        (self.state/'backups-verified').touch()

    def worker(self):
        try:
            with open('/srv/matheval/deploy.lock', 'a') as deployment:
                fcntl.flock(deployment, fcntl.LOCK_EX)
                self.helper.check_original()
                self.run('systemctl', 'is-active', self.rollback_unit+'.timer')
                self.helper.save(self.state/'rows-at-switch.json', self.helper.fingerprints())
                stat = Path('/var/lib/postgresql/17').stat()
                self.helper.save(self.state/'database-identity.json',
                                 [stat.st_dev, stat.st_ino, self.sql("SELECT oid FROM pg_database WHERE datname='matheval';")])
                with (self.state/'matheval-at-switch.dump').open('wb') as output:
                    self.run('runuser', '-u', 'postgres', '--', 'pg_dump', '--host=/run/postgresql',
                             '--create', '--format=custom', 'matheval', stdout=output)
                self.run(self.prepared['candidate']+'/bin/switch-to-configuration', 'test', visible=True)
                require(str(Path('/nix/var/nix/profiles/system').resolve()) == self.prepared['old_boot'], 'Le test a modifié le démarrage')
                # Le service Node peut finir son démarrage après systemd.
                for attempt in range(30):
                    ready = subprocess.run(['curl', '--fail', '--silent', '--max-time', '2',
                                            'http://127.0.0.1:3000/matheval/api/health'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if ready.returncode == 0:
                        break
                    time.sleep(1)
                self.verify_local()
                self.verify_backups()
                self.verify_local()
                (self.state/'tested').touch()
                print('Essai, accès PostgreSQL, conservation des lignes et restauration validés.', flush=True)
                while not any((self.state/x).exists() for x in ['committed', 'rollback-started']):
                    time.sleep(1)
        except Exception as error:
            (self.state/'worker-failed').write_text(type(error).__name__+': '+str(error)+'\n')
            raise

    def status(self):
        for filename, label in [('committed', 'committed'), ('rolled-back', 'rolled-back'),
                                ('rollback-started', 'rollback-started'), ('worker-failed', 'failed'),
                                ('tested', 'tested'), ('started', 'testing')]:
            if (self.state/filename).exists():
                print(label)
                return
        print('prepared')

    def commit(self):
        with (self.state/'finalize.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            require(commit_allowed(self.state), 'Enregistrement interdit après échec/retour ou avant les contrôles')
            require((self.state/'backups-verified').exists(), 'Sauvegardes non vérifiées')
            self.run('systemctl', 'is-active', self.rollback_unit+'.timer', self.worker_unit+'.service')
            self.verify_local()
            entry = Path('/etc/nixos/.configuration.nix.migration-'+self.short)
            entry.write_text('{ imports = [ '+self.prepared['installed']+'/hosts/hostinger/configuration.nix ]; }\n')
            entry.chmod(0o644)
            os.replace(entry, '/etc/nixos/configuration.nix')
            evaluated = json.loads(self.run('nix-instantiate', '--eval', '--strict', '--json',
                                            self.prepared['installed']+'/scripts/migration-config.nix',
                                            '--argstr', 'configuration', '/etc/nixos/configuration.nix',
                                            '-I', 'nixpkgs='+self.prepared['nixpkgs']))
            require(evaluated['toplevel'] == self.prepared['candidate'], 'L’entrée persistante ne désigne pas le candidat testé')
            self.run('nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', self.prepared['candidate'], visible=True)
            self.run(self.prepared['candidate']+'/bin/switch-to-configuration', 'boot', visible=True)
            require(str(Path('/nix/var/nix/profiles/system').resolve()) == self.prepared['candidate'], 'Profil de démarrage incorrect')
            self.verify_local()
            report = dict(self.prepared, operation_commit=self.operation, committed_at=time.time(),
                          live_verified=True, local_backup_restored=True, automatic_rollback_cancelled=True)
            self.helper.save(self.state/'committed.json', report)
            (self.state/'committed').touch()
            self.run('systemctl', 'stop', self.rollback_unit+'.timer')
            print('MIGRATION ENREGISTRÉE : '+json.dumps(report), flush=True)

    def abort(self):
        if (self.state/'committed').exists():
            print('Migration déjà enregistrée ; aucun retour déclenché.')
        elif (self.state/'started').exists():
            self.run('systemctl', 'start', self.rollback_unit+'.service', visible=True)
            require((self.state/'rolled-back').exists(), 'Retour arrière non confirmé')

    def preflight(self):
        self.helper.check_original()
        print('Précontrôle systemd : génération, Nixpkgs, sources, application et droits conformes.', flush=True)

    def recover(self):
        # Reprise ciblée de la première tentative, dont le journal prouve
        # l’échec du précontrôle avant toute activation du candidat.
        require(self.prepared['commit'] == '088d36c15f2fff9cecc4f25ff1b303fc29955042', 'Tentative non concernée')
        require((self.state/'worker-failed').read_text().strip() == 'RuntimeError: nix-instantiate : code 1', 'Échec différent')
        require(not any((self.state/name).exists() for name in
                        ['rows-at-switch.json', 'database-identity.json', 'tested', 'committed']),
                'L’essai a dépassé son précontrôle : réexaminer le retour')
        self.helper.check_original()
        require(self.run('systemctl', 'show', self.rollback_unit+'.timer', '--property=ActiveState', '--value').strip() == 'inactive', 'Ancien timer encore actif')
        original = self.state/'rollback.first-attempt.sh'
        require(not original.exists(), 'Récupération déjà engagée')
        shutil.copy2(self.state/'rollback.sh', original)
        self.rollback_script()
        self.run('systemctl', 'reset-failed', self.rollback_unit+'.service')
        self.run('systemctl', 'start', self.rollback_unit+'.service', visible=True)
        require((self.state/'rolled-back').exists(), 'Retour complet non confirmé')
        self.helper.check_original()
        self.helper.save(self.state/'recovery.json', dict(operation=self.operation, time=time.time(),
                                                       original_state_verified=True, complete_rollback_verified=True))
        print('Retour complet vérifié, y compris les droits SQL ; ancienne tentative conservée.', flush=True)


if __name__ == '__main__':
    mode, prepared, operation = sys.argv[1:]
    require(mode in {'plan', 'start', 'worker', 'status', 'commit', 'abort', 'preflight', 'recover'}, 'Opération inconnue')
    migration = Migration(prepared, operation)
    getattr(migration, mode)()
