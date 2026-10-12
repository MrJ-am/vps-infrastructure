"""Vrai OIDC Kanidm local : image C persistante ou qualification froide explicite."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE/'tests'))
from kanidm_reel import EchecQualification, FixtureOIDC


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--persistante', action='store_true')
    args = p.parse_args()
    if not os.environ.get('MRJAM_KANIDM') or not os.environ.get('MRJAM_CURL'):
        raise EchecQualification('paquet natif et Curl verrouillés requis')
    with FixtureOIDC(os.environ['MRJAM_KANIDM'], os.environ['MRJAM_CURL']) as fixture:
        if args.persistante:
            code = '(progn (asdf:load-system "mrjam-oidc/kanidm-tests") (assert (>= (uiop:symbol-call :mrjam-oidc-kanidm-tests :verifier '+json.dumps(str(fixture.path))+') 15)) (format t "OIDC-NATIF-TERMINE"))'
            result = subprocess.run(['python3', 'scripts/mcp-appel.py', 'cl-mcp', 'repl-eval'],
                                    input=json.dumps({'code': code}), capture_output=True, text=True, timeout=40)
            output = RACINE/'state/oidc-kanidm-evaluation-private.json'
            fd = os.open(output, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as file: file.write(result.stdout)
            response = json.loads(result.stdout)
            if result.returncode or response.get('error_context') or 'OIDC-NATIF-TERMINE' not in response.get('stdout', ''):
                # Contexte détaillé privé conservé, aucun token/secret dans stderr.
                raise EchecQualification('évaluation persistante non terminée ; diagnostic privé enregistré')
            output = response['stdout']
        else:
            env = dict(os.environ, MRJAM_KANIDM_FIXTURE=str(fixture.path))
            result = subprocess.run(['sbcl', '--script', 'tests/oidc-kanidm-froid.lisp'],
                                    env=env, capture_output=True, text=True, timeout=90)
            if result.returncode:
                # Ne pas imprimer les locaux d'une erreur pouvant contenir des tokens.
                diagnostic = RACINE/'state/oidc-kanidm-froid-private.log'
                fd=os.open(diagnostic,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600);os.fchmod(fd,0o600)
                with os.fdopen(fd,'w') as file:file.write(result.stdout+'\n'+result.stderr)
                raise EchecQualification('qualification froide non terminée ; diagnostic privé enregistré')
            output = result.stdout
            if output.count('Qualification OIDC Kanidm en image propre réussie.') != 1:
                raise EchecQualification('qualification froide sans marqueur terminal')
        counts = re.findall(r'OIDC Kanidm réel : (\d+) assertions terminées', output)
        if len(counts) != 1 or int(counts[0]) < 15:
            raise EchecQualification('assertions OIDC natives incomplètes')
        response = fixture.root/'reponse-jetons.json'
        if response.stat().st_mode & 0o777 != 0o600:
            raise EchecQualification('réponse privée non protégée')
        print(json.dumps({'assertions': int(counts[0]), 'kanidm_reel': True,
                          'image': 'persistante' if args.persistante else 'froide', 'production': False}))


if __name__ == '__main__':
    try: main()
    except EchecQualification as err:
        print(str(err), file=sys.stderr);sys.exit(1)
