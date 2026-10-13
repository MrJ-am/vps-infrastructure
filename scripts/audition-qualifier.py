"""Qualification centrale Audition sur PostgreSQL17.11 isolé, sans données réelles."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from assemblage import RACINE

POSTGRES = 'mirror.gcr.io/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'


def run(args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)


class PostgresAudition:
    """Fixture commune métier/Log : rôle non propriétaire et socket éphémère."""
    def __init__(self, container, socket, env):
        self.container, self.socket, self.env = container, socket, env
        self.docker = ['docker', '--host=unix:///var/run/docker.sock']
        self.dsn = 'host=' + str(socket) + ' dbname=postgres user=audition_app'

    def sql(self, query, base='postgres'):
        return run(self.docker + ['exec', '-i', self.container, 'psql', '-X', '-At',
            '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', base],
            input=query, capture_output=True, env=self.env).stdout

    def restaurer(self):
        dump = subprocess.run(self.docker + ['exec', self.container, 'pg_dump', '-U', 'postgres',
            '-Fc', '--schema=audition', 'postgres'], capture_output=True, check=True, env=self.env).stdout
        self.sql('CREATE DATABASE audition_restauration;')
        subprocess.run(self.docker + ['exec', '-i', self.container, 'pg_restore', '-U', 'postgres',
            '--exit-on-error', '-d', 'audition_restauration'], input=dump, capture_output=True, check=True, env=self.env)
        for table in ('versions', 'objets', 'requetes', 'audit', 'membres'):
            query = "SELECT encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') h FROM audition." + table + ' t) d;'
            if self.sql(query).strip() != self.sql(query, 'audition_restauration').strip():
                raise ValueError('Restauration incomplète : ' + table)


@contextmanager
def postgres_isole(administrateur='admin'):
    if administrateur not in ('admin', 'alice'):
        raise ValueError('Identité de fixture inconnue')
    docker = ['docker', '--host=unix:///var/run/docker.sock']
    env = {k: v for k, v in os.environ.items() if k not in
           ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')}
    with tempfile.TemporaryDirectory(prefix='audition-test-') as temp:
        socket = Path(temp) / 'socket'; socket.mkdir(); socket.chmod(0o777)
        container = run(docker + ['run', '-d', '--network=none', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
            '-v', str(socket) + ':/var/run/postgresql', POSTGRES, '-c', 'listen_addresses='],
            capture_output=True, env=env).stdout.strip()
        fixture = PostgresAudition(container, socket, env)
        try:
            for _ in range(100):
                ready = subprocess.run(docker + ['exec', container, 'pg_isready', '-h', '/var/run/postgresql'],
                    capture_output=True, env=env)
                if ready.returncode == 0 and run(docker + ['exec', container, 'cat', '/proc/1/comm'],
                    capture_output=True, env=env).stdout.strip() == 'postgres':
                    break
                time.sleep(0.2)
            else: raise ValueError('PostgreSQL isolé indisponible')
            fixture.sql('CREATE SCHEMA vision_gestion;')
            fixture.sql((RACINE / 'assemblage/audition/001-schema.sql').read_text())
            fixture.sql((RACINE / 'assemblage/audition/roles.sql').read_text())
            fixture.sql("INSERT INTO audition.administrateurs VALUES('" + administrateur + "',true);")
            yield fixture
        finally:
            run(docker + ['exec', '--user', 'root', container, 'chown',
                str(os.getuid()) + ':' + str(os.getgid()), '/var/run/postgresql'], capture_output=True, env=env)
            run(docker + ['exec', '--user', 'root', container, 'chmod', '0777', '/var/run/postgresql'], capture_output=True, env=env)
            run(docker + ['rm', '-f', '-v', container], capture_output=True, env=env)


def qualifier():
    exe = os.environ.get('MRJAM_SBCL') or shutil.which('sbcl')
    if not exe or run([exe, '--version'], capture_output=True).stdout.strip() != 'SBCL 2.6.4':
        raise ValueError('SBCL2.6.4 verrouillé requis ; aucune installation implicite')
    with postgres_isole() as fixture:
        debut = time.monotonic()
        run([exe, '--noinform', '--non-interactive', '--load', str(RACINE / 'tests/audition-charger.lisp'),
             '--eval', '(asdf:test-system "mrjam-audition/tests")'], cwd=RACINE,
             env=dict(fixture.env, AUDITION_TEST_DSN=fixture.dsn))
        restricted = fixture.sql('SET ROLE audition_app; SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user;')
        if '\nf\n' not in restricted: raise ValueError('Rôle métier trop puissant')
        fixture.sql("SET ROLE audition_app; BEGIN; SELECT set_config('audition.acteur','intrus',true); DO $$ BEGIN IF EXISTS(SELECT FROM audition.objets) THEN RAISE EXCEPTION 'fuite'; END IF; END $$; ROLLBACK;")
        fixture.restaurer()
        print(json.dumps({'audition': 'qualification_metier_reussie', 'postgres': '17.11',
                          'restauration': True, 'secondes': round(time.monotonic() - debut, 3), 'production': False}))


if __name__ == '__main__': qualifier()
