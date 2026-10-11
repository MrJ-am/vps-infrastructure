"""Qualification d'un exécutable construit proprement, AF_UNIX et redémarrage.

Utilise exclusivement la base synthétique préparée par matheval-composant.mjs.
Aucun accès au VPS, aucun secret réel, aucune identité OIDC prétendument vérifiée.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import time


def requete(chemin, texte):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(12)
        s.connect(str(chemin))
        s.sendall(texte)
        s.shutdown(socket.SHUT_WR)
        blocs = []
        while morceau := s.recv(65536):
            blocs.append(morceau)
    raw = b''.join(blocs)
    head, body = raw.split(b'\r\n\r\n', 1)
    return int(head.split(b' ', 2)[1]), head, body


def http(method, path, *, service='matheval', corps=b'', extra=b''):
    return (f'{method} {path} HTTP/1.1\r\nHost: localhost\r\nX-Mrjam-Service: {service}\r\n'.encode()
            + b'Content-Type: application/json\r\nOrigin: http://127.0.0.1:4173\r\nX-Matheval-Request: 1\r\nX-Mrjam-Remote-Addr: 127.0.0.1\r\n'
            + f'Content-Length: {len(corps)}\r\n'.encode() + extra + b'\r\n' + corps)


def qualifier(executable, fixture):
    c = json.loads(Path(fixture).read_text())
    assert 'host=127.0.0.1 ' in c['connexion'] and '_test' in c['connexion']
    contenu = Path(executable).read_bytes()
    for sentinelle in ('mot-é😀-de-passe-synthétique', 'mot-de-passe-test-synthetique', c['id']):
        assert sentinelle.encode() not in contenu, 'Fixture embarquée dans le build'
    with tempfile.TemporaryDirectory(prefix='mrjam-artefact-') as d:
        chemin = Path(d)/'metier.sock'
        activation=Path(d)/'activation';activation.write_text(c['activation']);activation.chmod(0o600)
        env = dict(os.environ, MRJAM_LIBCRYPTO=os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'),
                   MRJAM_LIBPQ=os.environ.get('MRJAM_LIBPQ','/lib/x86_64-linux-gnu/libpq.so.5'),
                   MATHEVAL_DSN=c['connexion'],MATHEVAL_BANK_VERSION=c['version'],
                   MATHEVAL_ORIGIN='http://127.0.0.1:4173',MATHEVAL_SETUP_HASH_FILE=str(activation),
                   VISION_DSN=c['connexion'],
                   VISION_DOCUMENT_ROOT=str(Path(d)/'sans-document'),MRJAM_SOCKET=str(chemin),MRJAM_INGRESS_UID=str(os.geteuid()))
        def demarrer():
            p = subprocess.Popen([str(Path(executable).resolve())], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for _ in range(100):
                if chemin.exists(): break
                if p.poll() is not None: raise AssertionError('Démarrage refusé')
                time.sleep(.05)
            else: raise AssertionError('Socket absent')
            assert stat.S_IMODE(chemin.stat().st_mode)==0o660
            return p
        def arreter(p):
            p.terminate()
            try: p.wait(timeout=12)
            except subprocess.TimeoutExpired: p.kill();p.wait();raise AssertionError('Arrêt non borné')
            p.stderr.close()
            # SIGTERM peut quitter sans unwind Lisp : RuntimeDirectory géré par
            # systemd en production, suppression du seul socket de cette fixture.
            chemin.unlink(missing_ok=True)
        p=demarrer()
        try:
            status,h,b=requete(chemin,http('GET','/matheval/api/health'))
            assert status==200 and json.loads(b)=={'status':'ok','version':c['version']}
            assert requete(chemin,http('GET','/healthz',service='vision'))[0]==200
            for bad,expected in [
                (http('GET','/matheval/api/health',extra=b'Content-Length: 0\r\n'),400),
                (http('GET','/matheval/api/health',extra=b'Transfer-Encoding: chunked\r\n'),400),
                (http('GET','/matheval/api/health',extra=b'X-Mrjam-Service: vision\r\n'),400),
                (http('GET','/matheval/api/health',extra=b'X-Mrjam-Remote-Addr: 192.0.2.1\r\n'),400),
                (http('GET','/matheval/api/health',corps=b'{}'),400),
                (http('GET','/matheval/api/health',service='autre'),400),
                (b'GET /matheval/api/health HTTP/1.1\n\n',400),
                (http('GET','/matheval/api/health',extra=b'Long: '+b'a'*8200+b'\r\n'),431),
                (http('GET','/matheval/api/health?level=%ZZ'),400),
                (http('POST','/matheval/api/sessions',corps=b'\xff'),400),
            ]:
                assert requete(chemin,bad)[0]==expected, 'Framing refusé incorrectement'
            data={'id':c['id'],'secret':'a'*64,'bankVersion':c['version'],
                  'levels':[json.loads(Path(c['bankPath']).read_text())['questions'][0]['level']],'seed':4294967295}
            assert requete(chemin,http('POST','/matheval/api/sessions',corps=json.dumps(data).encode()))[0]==201
            sauvegarde=next(x['data'] for x in c['cases'] if x['method']=='PUT')
            assert requete(chemin,http('PUT','/matheval/api/sessions/'+c['id'],corps=json.dumps(sauvegarde).encode(),
                                      extra=('X-Session-Token: '+'a'*64+'\r\n').encode()))[0]==200
            lecture=http('GET','/matheval/api/sessions/'+c['id'],extra=('X-Session-Token: '+'a'*64+'\r\n').encode())
            status,_,avant=requete(chemin,lecture)
            assert status==200 and json.loads(avant)['revision']==1
            assert json.loads(avant)['snapshot']==sauvegarde['snapshot']
            assert requete(chemin,http('GET','/matheval/api/sessions/'+c['id'],extra=('X-Session-Token: '+'b'*64+'\r\n').encode()))[0]==401
            admin=next(x['data'] for x in c['cases'] if x['setCookie']=='admin1')
            # Origine refusée et JSON illisible interviennent avant le budget,
            # conformément au middleware de référence.
            for _ in range(9):
                mauvais=http('POST','/matheval/api/admin/login',corps=b'{}').replace(b'Origin: http://127.0.0.1:4173',b'Origin: https://autre.test')
                assert requete(chemin,mauvais)[0]==403
                assert requete(chemin,http('POST','/matheval/api/admin/login',corps=b'{'))[0]==400
                assert requete(chemin,http('POST','/matheval/api/admin/login',corps=b'true'))[0]==400
            status,h,b=requete(chemin,http('POST','/matheval/api/admin/setup',corps=json.dumps(admin).encode()))
            assert status==200
            assert b'RateLimit: "8-in-15min"; r=7;' in h
            assert b'RateLimit-Policy: "8-in-15min"; q=8; w=900; pk=:' in h
            cookie=next(x.split(b': ',1)[1].split(b';',1)[0] for x in h.split(b'\r\n') if x.lower().startswith(b'set-cookie:'))
            admin_read=http('GET','/matheval/api/admin/me',extra=b'Cookie: '+cookie+b'\r\n')
            assert requete(chemin,admin_read)[0]==200
            # L'activation a consommé un des huit essais de connexion. La
            # validation JSON échoue vite ; elle ne contourne pas le budget.
            for _ in range(7):
                assert requete(chemin,http('POST','/matheval/api/admin/login',corps=b'{}'))[0]==400
            code,h,b=requete(chemin,http('POST','/matheval/api/admin/login',corps=b'{}'))
            assert code==429 and b'Retry-After:' in h
            assert b'RateLimit: "8-in-15min"; r=0;' in h
            assert b'X-Content-Type-Options: nosniff' in h and b'Content-Security-Policy:' in h
            assert json.loads(b)['error']=='Trop de tentatives. Réessayez dans quelques minutes.'
            assert requete(chemin,admin_read)[0]==200
        finally: arreter(p)
        env['MRJAM_INGRESS_UID']=str(os.geteuid()+1)
        p=demarrer()
        try:
            try:
                requete(chemin,http('GET','/healthz',service='vision',extra=b'X-Vision-Authenticated: 1\r\nX-Mrj-User: alice\r\n'))
            except (ConnectionResetError,ValueError,BrokenPipeError): pass
            else: raise AssertionError('UID pair non autorisé accepté')
        finally: arreter(p)
        env['MRJAM_INGRESS_UID']=str(os.geteuid())
        p=demarrer()
        try:
            status,_,apres=requete(chemin,lecture)
            assert status==200 and json.loads(avant)==json.loads(apres), 'État perdu après redémarrage'
            assert requete(chemin,admin_read)[0]==200, 'Session SQL perdue au redémarrage'
        finally: arreter(p)
    print('Artefact propre : routage HTTP réel AF_UNIX, framing hostile, état SQL conservé après redémarrage.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--executable',required=True);p.add_argument('--fixture',required=True)
    a=p.parse_args();qualifier(a.executable,a.fixture)
