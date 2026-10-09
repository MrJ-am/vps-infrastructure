"""Qualifier Keycloak natif avec JDBC Unix et PostgreSQL peer, sans TCP.

Conteneurs et comptes synthétiques ; aucune adresse distante configurable.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

spec = importlib.util.spec_from_file_location('restauration', Path(__file__).with_name('keycloak-postgresql-restauration.py'))
natif = importlib.util.module_from_spec(spec); spec.loader.exec_module(natif)


def verifier(jar, common, native):
    assert all(p.is_file() for p in (jar, common, native))
    nom = 'qualification-unix-' + uuid.uuid4().hex[:12]
    pg = nom + '-pg'; idp = nom + '-idp'
    with tempfile.TemporaryDirectory() as dossier:
        root = Path(dossier); root.chmod(0o755)
        socket = root / 'socket'; socket.mkdir(mode=0o700)
        (root / 'pg_hba.conf').write_text('local all postgres peer\nlocal identite_unix keycloak peer map=qualification\nlocal all all reject\n')
        (root / 'pg_ident.conf').write_text('qualification postgres keycloak\n')
        for fichier in ('pg_hba.conf', 'pg_ident.conf'): (root / fichier).chmod(0o644)
        try:
            natif.commande('docker', 'run', '--rm', '--network', 'none', '--user', '0',
                '-v', str(root) + ':/qualification', '--entrypoint', 'chown',
                'pgvector/pgvector:0.8.0-pg17', '999:999', '/qualification/socket')
            natif.commande('docker', 'run', '-d', '--name', pg, '--network', 'none',
                '-v', str(root) + ':/qualification', '-e', 'POSTGRES_PASSWORD=uniquement-initialisation-synthetique',
                '-v', str(socket) + ':/var/run/postgresql',
                'pgvector/pgvector:0.8.0-pg17', '-c', 'listen_addresses=',
                '-c', 'unix_socket_permissions=0700',
                '-c', 'hba_file=/qualification/pg_hba.conf', '-c', 'ident_file=/qualification/pg_ident.conf')
            for _ in range(60):
                try:
                    natif.commande('docker', 'exec', '--user', '999', pg, 'psql', '-X',
                        '-h', '/var/run/postgresql', '-U', 'postgres', '-c', 'SELECT 1'); break
                except RuntimeError:
                    if natif.commande('docker', 'inspect', '--format', '{{.State.Running}}', pg).strip() != b'true':
                        raise RuntimeError('Le conteneur PostgreSQL Unix synthétique s’est arrêté') from None
                    time.sleep(1)
            else: raise RuntimeError('PostgreSQL Unix synthétique indisponible')
            def sql(texte):
                return natif.commande('docker', 'exec', '--user', '999', pg, 'psql', '-X', '-At',
                    '--set=ON_ERROR_STOP=1', '-h', '/var/run/postgresql', '-U', 'postgres', '-c', texte)
            sql('CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
            sql('CREATE DATABASE identite_unix OWNER keycloak')
            assert sql('SHOW listen_addresses').strip() == b''
            assert sql("SELECT auth_method FROM pg_hba_file_rules WHERE 'keycloak'=ANY(user_name)").strip() == b'peer'
            assert sql("SELECT rolpassword IS NULL FROM pg_authid WHERE rolname='keycloak'").strip() == b't'
            url = ('jdbc:postgresql://localhost/identite_unix?'
                'socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory$FactoryArg&'
                'socketFactoryArg=/run/postgresql/.s.PGSQL.5432&sslMode=disable')
            natif.commande('docker', 'run', '-d', '--name', idp, '--network', 'host', '--user', '999:0',
                '-v', str(socket) + ':/run/postgresql:ro',
                '-v', str(jar) + ':/opt/keycloak/providers/mrjam-identite.jar:ro',
                '-v', str(common) + ':/opt/keycloak/providers/junixsocket-common.jar:ro',
                '-v', str(native) + ':/opt/keycloak/providers/junixsocket-native-common.jar:ro',
                '-e', 'KC_DB=postgres', '-e', 'KC_DB_URL=' + url, '-e', 'KC_DB_USERNAME=keycloak',
                '-e', 'KC_BOOTSTRAP_ADMIN_USERNAME=qualification',
                '-e', 'KC_BOOTSTRAP_ADMIN_PASSWORD=uniquement-test-local',
                natif.IMAGE, 'start-dev', '--http-host=127.0.0.1', '--http-port=38091')
            natif.attendre(38091)
            assert natif.api(38091, '/admin/realms/master', jeton=natif.administrateur(38091))['realm'] == 'master'
            assert sql("SELECT count(*)>0 FROM pg_stat_activity WHERE usename='keycloak' AND client_addr IS NULL").strip() == b't'
            mauvais = subprocess.run(['docker', 'exec', '--user', '1000', pg, 'psql', '-X',
                '-h', '/var/run/postgresql', '-U', 'keycloak', '-d', 'identite_unix', '-c', 'SELECT 1'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert mauvais.returncode != 0
            print(json.dumps(dict(keycloak_natif=True, jdbc_unix=True, peer_sans_mot_de_passe=True,
                postgresql_tcp_ferme=True, autre_uid_refuse=True)))
        finally:
            for conteneur in (idp, pg):
                subprocess.run(['docker', 'rm', '-f', conteneur], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--user', '0',
                '-v', str(root) + ':/qualification', '--entrypoint', 'chown',
                'pgvector/pgvector:0.8.0-pg17', '-R', str(os.getuid()) + ':' + str(os.getgid()), '/qualification'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for nom in ('jar', 'common', 'native'): p.add_argument('--' + nom, type=Path, required=True)
    a = p.parse_args(); verifier(a.jar.resolve(), a.common.resolve(), a.native.resolve())
