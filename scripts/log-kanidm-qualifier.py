"""Sessions Lisp persistantes avec IdP réel isolé. Aucun compte de production."""
import importlib.util
import argparse
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import queue
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from kanidm_reel import EchecQualification, KanidmLocal
from kanidm_politiques import creer_neuf_mfa, code_totp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--persistante', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('pont_local', ROOT/'scripts/mcp-appel.py')
    pont = importlib.util.module_from_spec(spec); spec.loader.exec_module(pont)
    def evaluer_persistante(code):
        r = pont.requete('cl-mcp', 'tools/call', {'name': 'repl-eval', 'arguments': {'code': code}})
        if r.get('error_context') or r.get('isError'):
            dest = ROOT/'state/log-kanidm-diagnostic-prive.json'
            fd = os.open(dest, os.O_CREAT|os.O_WRONLY|os.O_TRUNC, 0o600); os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as s: json.dump(r, s)
            raise EchecQualification('sessions Lisp : diagnostic privé enregistré, aucun succès attesté')
        if 'LOG-TERMINE' not in r.get('stdout', ''):
            raise EchecQualification('absence de marqueur terminal Lisp')

    paquet = os.environ.get('MRJAM_KANIDM'); curl = os.environ.get('MRJAM_CURL')
    if not paquet or not curl: raise EchecQualification('outils natifs verrouillés requis')
    with KanidmLocal(paquet, curl) as n:
        qualified_after = int(time.time())
        user = creer_neuf_mfa(n)
        # La réauthentification native exige réellement TOTP puis password.
        jar=n.root/'reauth-fixture.cookies'; jar.touch(mode=0o600)
        status, auth=n.http('/v1/reauth','token',token=user,cookies=jar)
        if status!=200 or auth.get('state',{}).get('continue')!=['totp']:
            raise EchecQualification('réauthentification native sans TOTP')
        status, auth=n.http('/v1/auth',{'step':{'cred':{'totp':code_totp(n.mfa_secret)}}},cookies=jar)
        if status!=200 or auth.get('state',{}).get('continue')!=['password']:
            raise EchecQualification('réauthentification native sans password après TOTP')
        status, auth=n.http('/v1/auth',{'step':{'cred':{'password':n.password}}},cookies=jar)
        if status!=200 or 'success' not in auth.get('state',{}):
            raise EchecQualification('réauthentification MFA native refusée')
        user=auth['state']['success']
        alice_uuid, alice_nom, alice_mail = n.uuid, n.nom, n.mail
        n.nom = 'fixture-bob'; n.mail = 'fixture-bob@example.test'
        bob = creer_neuf_mfa(n); bob_uuid = n.uuid
        n.uuid, n.nom, n.mail = alice_uuid, alice_nom, alice_mail
        secret = n.creer_client_oidc()
        fixture = n.root/'sessions-fixture.json'; result = n.root/'sessions-resultat.json'
        http = n.root/'http-reponse.txt'
        fixture.touch(mode=0o600); result.touch(mode=0o600); http.touch(mode=0o600)
        params = dict(uuid=n.uuid, secret=secret, curl=str(n.curl), ca=str(n.ca), port=n.port,
                      base=str(n.root/'sessions.sqlite'), resultat=str(result), http=str(http), mail=n.mail,
                      qualifie_a=qualified_after, bob_uuid=bob_uuid)
        fixture.write_text(json.dumps(params))
        path = json.dumps(str(fixture))
        proc = None
        lignes = queue.Queue()
        if not args.persistante:
            diagnostic = ROOT/'state/log-kanidm-froid-prive.log'
            fd = os.open(diagnostic, os.O_CREAT|os.O_WRONLY|os.O_TRUNC, 0o600); os.fchmod(fd, 0o600)
            journal = os.fdopen(fd, 'w')
            proc = subprocess.Popen(['sbcl', '--script', 'tests/log-kanidm-froid.lisp'],
                                    env=dict(os.environ, MRJAM_LOG_FIXTURE=str(fixture)),
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True)
            def lire_sortie():
                for line in proc.stdout:
                    journal.write(line); journal.flush()
                    if line.strip() == 'LOG-TERMINE': lignes.put(True)
                lignes.put(False)
            threading.Thread(target=lire_sortie, daemon=True).start()
        def evaluer(code, commande):
            if args.persistante: return evaluer_persistante(code)
            proc.stdin.write(commande+'\n'); proc.stdin.flush()
            try: termine = lignes.get(timeout=60)
            except queue.Empty: termine = False
            if not termine:
                proc.kill(); proc.wait(); journal.close()
                raise EchecQualification('processus froid non terminé ; diagnostic privé enregistré')
        try:
            evaluer('(progn (asdf:load-asd #P"'+str(ROOT/'mrjam-log.asd')+'") '
                    '(asdf:load-system "mrjam-log/kanidm-tests") '
                    '(assert (uiop:symbol-call :mrjam-log-tests :verifier)) '
                    '(uiop:symbol-call :mrjam-log-kanidm-tests :preparer '+path+') '
                    '(format t "LOG-TERMINE"))', 'preparer')
            start = json.loads(result.read_text()); q = parse_qs(urlsplit(start['uri']).query)
            code = n.autoriser_code(user, 'mrjam-vision', 'vision.mrj.am',
                                   q['state'][0], q['nonce'][0], q['code_challenge'][0])
            params.update(state=q['state'][0], code=code, cookie=start['cookie'])
            fixture.write_text(json.dumps(params))
            evaluer('(progn (uiop:symbol-call :mrjam-log-kanidm-tests :terminer '+path+') '
                    '(format t "LOG-TERMINE"))', 'terminer')
            evaluer('(progn (uiop:symbol-call :mrjam-log-kanidm-tests :preparer-bob '+path+') '
                    '(format t "LOG-TERMINE"))', 'preparer-bob')
            start = json.loads(result.read_text()); q = parse_qs(urlsplit(start['uri']).query)
            code = n.autoriser_code(bob, 'mrjam-vision', 'vision.mrj.am',
                                   q['state'][0], q['nonce'][0], q['code_challenge'][0])
            params.update(state=q['state'][0], code=code, cookie=start['cookie'])
            fixture.write_text(json.dumps(params))
            evaluer('(progn (uiop:symbol-call :mrjam-log-kanidm-tests :terminer-bob '+path+') '
                    '(format t "LOG-TERMINE"))', 'terminer-bob')
            n.arreter(); n.demarrer()
            evaluer('(progn (uiop:symbol-call :mrjam-log-kanidm-tests :reprendre '+path+') '
                    '(uiop:symbol-call :mrjam-log-kanidm-tests :logout) (format t "LOG-TERMINE"))', 'reprendre')
            if proc:
                proc.stdin.close()
                try: retour = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(); journal.close()
                    raise EchecQualification('processus froid ne termine pas')
                journal.close()
                if retour: raise EchecQualification('processus froid refusé')
        finally:
            if proc:
                if proc.poll() is None:
                    proc.kill(); proc.wait()
                if not journal.closed: journal.close()
        print(json.dumps({'sessions_lisp_kanidm_reel': True, 'restart_idp': True,
                          'isolation_hotes': True, 'compte_suspendu_refuse': True,
                          'code_non_rejouable': True, 'logout_effectif': True,
                          'image': 'persistante' if args.persistante else 'froide', 'production': False}))


if __name__ == '__main__':
    try: main()
    except EchecQualification as error:
        print(str(error), file=sys.stderr); sys.exit(1)
