"""Paquet Nix optimisé exact : PostgreSQL peer/Unix, sans réseau ni données réelles.

Ces conteneurs qualifient le lanceur et le paquet. DynamicUser et systemd natifs
ne sont attestés que par le workflow distinct exécuté sur le VPS.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
REFUS_PRIVE = b''


def commande(*args, entree=None, timeout=150):
    global REFUS_PRIVE
    r = subprocess.run([str(a) for a in args], input=entree, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout)
    if r.returncode:
        REFUS_PRIVE = (r.stdout + r.stderr)[-65536:]
        raise RuntimeError('Commande du paquet optimisé synthétique refusée')
    return r.stdout.decode().strip()


def verifier(paquet, image_outils, volume, racine_volume, diagnostic=None):
    nom = 'qualification-optimise-' + uuid.uuid4().hex[:10]; pg = nom + '-pg'; idp = nom + '-idp'
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); root.chmod(0o755)
        for nom_dossier in ('pg-runtime', 'runtime', 'credentials'):
            (root / nom_dossier).mkdir(mode=0o711 if nom_dossier == 'pg-runtime' else 0o700)
        secret = secrets.token_urlsafe(32)
        (root / 'credentials/bootstrap').write_text(secret)
        (root / 'credentials/bootstrap').chmod(0o600)
        for fichier, amont in (('demarrer.sh', 'vision-identite-unix-demarrer.sh'),
                ('postgresql.sh', 'vision-identite-unix-postgresql.sh'), ('qualification-http.py', 'vision-identite-unix-http.py')):
            shutil.copyfile(ROOT / 'scripts' / amont, root / fichier); (root / fichier).chmod(0o444)
        try:
            commande('docker', 'run', '--rm', '--network', 'none', '-v', str(root) + ':/test',
                '--entrypoint', 'chown', 'pgvector/pgvector:0.8.0-pg17', '-R', '999:999', '/test')
            commande('docker', 'run', '-d', '--name', pg, '--network', 'none', '--user', '999:999',
                '-v', str(root) + ':/test', '--entrypoint', 'sh', 'pgvector/pgvector:0.8.0-pg17',
                '/test/postgresql.sh', '/usr/lib/postgresql/17/bin', '/test/pg-runtime', 'postgres')
            def sql(q):
                return commande('docker', 'exec', '--user', '999', pg, 'psql', '-XAtq',
                    '-v', 'ON_ERROR_STOP=1', '-h', '/test/pg-runtime/socket', '-U', 'postgres', '-c', q)
            for _ in range(60):
                try:
                    if sql('SELECT 1') == '1': break
                except RuntimeError: time.sleep(1)
            else: raise RuntimeError('PostgreSQL synthétique indisponible')
            sql('CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
            sql('CREATE DATABASE identite_unix OWNER keycloak')
            sql('REVOKE ALL ON DATABASE identite_unix FROM PUBLIC')
            commande('docker', 'run', '-d', '--name', idp, '--network', 'none', '--user', '999:999',
                '-v', volume + ':' + racine_volume + ':ro',
                '-v', str(root) + ':/test', '-e', 'CREDENTIALS_DIRECTORY=/test/credentials',
                image_outils, 'sh', '/test/demarrer.sh',
                paquet, '/test/runtime', '/test/pg-runtime/socket')
            http = json.loads(commande('docker', 'exec', '-i', idp, 'python3',
                '/test/qualification-http.py', entree=json.dumps({'secret': secret}).encode(), timeout=160))
            assert all(http.values())
            assert sql("SELECT count(*)>0 FROM pg_stat_activity WHERE usename='keycloak' AND client_addr IS NULL") == 't'
            assert sql("SELECT current_setting('listen_addresses')='' AND current_setting('server_encoding')='UTF8' AND rolpassword IS NULL FROM pg_authid WHERE rolname='keycloak'") == 't'
            mauvais = subprocess.run(['docker', 'exec', '--user', '0', pg, 'psql', '-XAtq',
                '-h', '/test/pg-runtime/socket', '-U', 'keycloak', '-d', 'identite_unix', '-c', 'SELECT 1'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            assert mauvais.returncode != 0
            print(json.dumps(dict(**http, paquet_nix=True, jdbc_unix=True, peer=True,
                autre_uid_refuse=True, postgresql_tcp_ferme=True, conteneurs_synthetiques=True)), flush=True)
        except Exception:
            if diagnostic:
                fd = os.open(diagnostic, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as f:
                    f.write(REFUS_PRIVE)
                    for c in (idp, pg):
                        r = subprocess.run(['docker', 'logs', c], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                        f.write((r.stdout + r.stderr)[-65536:])
            raise
        finally:
            for c in (idp, pg): subprocess.run(['docker', 'rm', '-f', c], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            commande('docker', 'run', '--rm', '--network', 'none', '-v', str(root) + ':/test',
                '--entrypoint', 'chown', 'pgvector/pgvector:0.8.0-pg17', '-R', str(os.getuid()) + ':' + str(os.getgid()), '/test')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--paquet', required=True)
    p.add_argument('--image-outils', default='debian:bookworm-slim')
    p.add_argument('--volume', default='/nix/store')
    p.add_argument('--racine-volume', choices=('/nix', '/nix/store'), default='/nix/store')
    p.add_argument('--diagnostic-prive', type=Path)
    a = p.parse_args(); verifier(a.paquet, a.image_outils, a.volume, a.racine_volume, a.diagnostic_prive)
