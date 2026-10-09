"""Lanceurs configurés, import sans personne et peer dans des conteneurs sans réseau."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def http(secret):
    class SansRedirection(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_a, **_k): return None
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), SansRedirection())
    def api(path, data=None, token=None):
        entetes = {'X-Forwarded-Proto': 'https'}
        if data: entetes['Content-Type'] = 'application/x-www-form-urlencoded'
        if token: entetes['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request('http://127.0.0.1:8085' + path,
            urllib.parse.urlencode(data).encode() if data else None, entetes)
        with client.open(req, timeout=5) as r: return json.loads(r.read(2 * 1024 * 1024))
    for _ in range(120):
        try: d = api('/realms/mrjam/.well-known/openid-configuration'); break
        except (OSError, urllib.error.HTTPError): time.sleep(1)
    else: raise RuntimeError('Identité synthétique indisponible')
    assert d['issuer'] == 'https://log.mrj.am/realms/mrjam'
    token = api('/realms/master/protocol/openid-connect/token', dict(client_id='admin-cli',
        username='amorcage-local', password=secret, grant_type='password'))['access_token']
    realm = api('/admin/realms/mrjam', token=token)
    assert realm['registrationAllowed'] is False and realm['loginTheme'] == 'mrjam'
    assert realm['smtpServer']['starttls'] == 'true' and realm['smtpServer']['auth'] == 'true'
    users = api('/admin/realms/mrjam/users?max=100', token=token)
    # Cette API exclut les comptes de service sur la version épinglée.
    assert users == []
    clients = api('/admin/realms/mrjam/clients', token=token)
    techniques = [c for c in clients if c.get('serviceAccountsEnabled')]
    assert {c['clientId'] for c in techniques} == {'mrjam-cycle', 'mrjam-admission', 'mrjam-fermeture'}
    for c in techniques:
        compte = api('/admin/realms/mrjam/clients/' + c['id'] + '/service-account-user', token=token)
        assert compte['enabled'] and compte['username'] == 'service-account-' + c['clientId']
    info = api('/admin/serverinfo', token=token)
    assert info['systemInfo']['version'] == '26.7.3'
    assert 'mrjam-courriel' in info['providers']['authenticator']['providers']
    return dict(issuer_canonique=True, import_initial=True, aucune_personne=True,
        inscription_native_fermee=True, smtp_tls_configure_sans_envoi=True, spi_charge=True)


def qualifier(resume, image, volume, racine_volume, diagnostic):
    spec = importlib.util.spec_from_file_location('optimise', ROOT / 'tests/keycloak-unix-optimise.py')
    outils = importlib.util.module_from_spec(spec); spec.loader.exec_module(outils)
    cmd = outils.commande
    r = json.loads(Path(resume).read_text())
    nom = 'qualification-amorcage-' + uuid.uuid4().hex[:10]; pg = nom + '-pg'; idp = nom + '-idp'
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); root.chmod(0o755)
        secret = secrets.token_urlsafe(32)
        try:
            preparation = '''import importlib.util,json,os,secrets,shutil
from pathlib import Path
root=Path('/test')
for nom,uid,mode in [('donnees',999,0o700),('socket',999,0o711),('runtime',1001,0o700),('credentials',1001,0o700)]:
    p=root/nom;p.mkdir(mode=mode);p.chmod(mode);os.chown(p,uid,uid)
spec=importlib.util.spec_from_file_location('identite','/qualification/scripts/identite-preparer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
prive=root/'import-prive';prive.mkdir(mode=0o700)
m.preparer(Path('/qualification/operations/identite/realm.json'),prive)
realm=json.loads((prive/'mrjam-realm.json').read_text())
realm['smtpServer']={'host':'smtp.protonmail.ch','port':'587','starttls':'true','ssl':'false',
  'auth':'true','user':'synthetique@example.invalid','from':'synthetique@example.invalid','password':secrets.token_urlsafe(32)}
c=root/'credentials/realm-import';c.write_text(json.dumps(realm));c.chmod(0o600);os.chown(c,1001,1001)
c=root/'credentials/amorcage-admin';c.write_bytes(os.read(0,4096));c.chmod(0o600);os.chown(c,1001,1001)
shutil.copyfile('/qualification/tests/identite-amorcage-integration.py',root/'verifier-http.py')
(root/'verifier-http.py').chmod(0o444)
'''
            cmd('docker', 'run', '--rm', '-i', '--network', 'none', '--user', '0',
                '-v', str(root) + ':/test', '-v', str(ROOT) + ':/qualification:ro',
                image, 'python3', '-c', preparation, entree=(secret + '\n').encode())
            lancement = '''set -eu
useradd --uid 1001 --no-create-home keycloak
runuser -u postgres -- sh "$1" initialiser "$2" /var/lib/mrjam-amorcage-postgresql /run/mrjam-amorcage-postgresql
runuser -u postgres -- "$2/pg_ctl" -D /var/lib/mrjam-amorcage-postgresql -l /var/lib/mrjam-amorcage-postgresql/prive.log -w -o "-c listen_addresses='' -c unix_socket_directories=/run/mrjam-amorcage-postgresql -c unix_socket_permissions=0777 -c port=5432" start
runuser -u postgres -- sh "$1" configurer "$2" /var/lib/mrjam-amorcage-postgresql /run/mrjam-amorcage-postgresql
exec tail -f /dev/null
'''
            cmd('docker', 'run', '-d', '--name', pg, '--network', 'none', '--user', '0',
                '-v', volume + ':' + racine_volume + ':ro', '-v', str(root) + ':/test',
                '-v', str(root / 'donnees') + ':/var/lib/mrjam-amorcage-postgresql',
                '-v', str(root / 'socket') + ':/run/mrjam-amorcage-postgresql',
                '--entrypoint', 'sh', 'pgvector/pgvector:0.8.0-pg17', '-c', lancement, 'amorcage',
                r['lanceur_cluster'], r['postgres_paquet'] + '/bin')
            def sql(q, uid='999', role='postgres', base='postgres'):
                return cmd('docker', 'exec', '--user', uid, pg, r['postgres_paquet'] + '/bin/psql',
                    '-XAtq', '-v', 'ON_ERROR_STOP=1', '-h', '/run/mrjam-amorcage-postgresql', '-p', '5432',
                    '-U', role, '-d', base, '-c', q)
            for _ in range(60):
                try:
                    if sql("SELECT pg_get_userbyid(datdba)='keycloak' FROM pg_database WHERE datname='mrjam_identite'") == 't': break
                except RuntimeError: time.sleep(1)
            else: raise RuntimeError('Cluster privé synthétique indisponible')
            assert sql('SELECT 1', uid='1001', role='keycloak', base='mrjam_identite') == '1'
            assert sql("SELECT rolpassword IS NULL AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolbypassrls FROM pg_authid WHERE rolname='keycloak'") == 't'
            refuse = subprocess.run(['docker', 'exec', '--user', '0', pg,
                r['postgres_paquet'] + '/bin/psql', '-XAtq', '-h', '/run/mrjam-amorcage-postgresql', '-p', '5432',
                '-U', 'keycloak', '-d', 'mrjam_identite', '-c', 'SELECT 1'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            assert refuse.returncode != 0
            mauvais_socket = subprocess.run(['docker', 'exec', '--user', '999', pg, 'sh',
                r['lanceur_cluster'], 'configurer', r['postgres_paquet'] + '/bin',
                '/var/lib/mrjam-amorcage-postgresql', '/run/postgresql'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            assert mauvais_socket.returncode != 0
            # Une relance conserve les données et refuse un rôle devenu superuser.
            cmd('docker', 'exec', '--user', '999', pg, 'sh', r['lanceur_cluster'], 'configurer',
                r['postgres_paquet'] + '/bin', '/var/lib/mrjam-amorcage-postgresql', '/run/mrjam-amorcage-postgresql')
            sql('ALTER ROLE keycloak SUPERUSER')
            refuse = subprocess.run(['docker', 'exec', '--user', '999', pg, 'sh', r['lanceur_cluster'],
                'configurer', r['postgres_paquet'] + '/bin', '/var/lib/mrjam-amorcage-postgresql', '/run/mrjam-amorcage-postgresql'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            assert refuse.returncode != 0
            sql('ALTER ROLE keycloak NOSUPERUSER')
            cmd('docker', 'run', '-d', '--name', idp, '--network', 'none', '--user', '1001:1001',
                '-v', volume + ':' + racine_volume + ':ro', '-v', str(root) + ':/test',
                '-v', str(root / 'socket') + ':/run/mrjam-amorcage-postgresql',
                '-v', str(root / 'runtime') + ':/run/mrjam-amorcage-identite',
                '-e', 'CREDENTIALS_DIRECTORY=/test/credentials', image, 'sh',
                r['lanceur_identite'], r['paquet'], '/run/mrjam-amorcage-identite', '/run/mrjam-amorcage-postgresql', r['themes'])
            controle = json.loads(cmd('docker', 'exec', '-i', '--user', '1001:1001', idp,
                'python3', '/test/verifier-http.py', '--http', entree=secret.encode(), timeout=150))
            assert all(controle.values())
            assert sql("SELECT count(*)>0 FROM pg_stat_activity WHERE usename='keycloak' AND datname='mrjam_identite' AND client_addr IS NULL") == 't'
            assert sql("SELECT current_setting('listen_addresses')='' AND current_setting('server_encoding')='UTF8'") == 't'
            print(json.dumps(dict(**controle, postgres_prive=True, peer=True, autre_uid_refuse=True,
                role_privilegie_refuse=True, relance_sans_perte=True, conteneurs_sans_reseau=True)), flush=True)
        except Exception:
            if diagnostic:
                fd = os.open(diagnostic, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as f:
                    f.write(outils.REFUS_PRIVE)
                    for c in (idp, pg):
                        log = subprocess.run(['docker', 'logs', c], capture_output=True, timeout=10)
                        f.write((log.stdout + log.stderr)[-65536:])
            raise
        finally:
            for c in (idp, pg):
                subprocess.run(['docker', 'rm', '-f', c], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=30)
            cmd('docker', 'run', '--rm', '--network', 'none', '-v', str(root) + ':/test',
                '--entrypoint', 'chown', 'pgvector/pgvector:0.8.0-pg17',
                '-R', str(os.getuid()) + ':' + str(os.getgid()), '/test')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--http', action='store_true')
    p.add_argument('--resume'); p.add_argument('--image-outils')
    p.add_argument('--volume', default='/nix/store')
    p.add_argument('--racine-volume', choices=('/nix', '/nix/store'), default='/nix/store')
    p.add_argument('--diagnostic-prive', type=Path)
    a = p.parse_args()
    if a.http: print(json.dumps(http(sys.stdin.read(4096))), flush=True)
    else: qualifier(a.resume, a.image_outils, a.volume, a.racine_volume, a.diagnostic_prive)
