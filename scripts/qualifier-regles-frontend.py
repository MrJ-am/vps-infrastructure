"""Tests des règles et preuve que la vraie commande bloque une violation volontaire."""
import json
import os
from pathlib import Path
import subprocess
import sys
from assemblage import RACINE, chemins_sources


def main():
    sources=chemins_sources()
    env=dict(os.environ,ELM_HOME=str(RACINE/'state/elm-home'))
    subprocess.run([str(sources['matheval']/'docs/node_modules/.bin/elm-test'),
                    '--compiler',str(sources['matheval']/'docs/node_modules/.bin/elm'),
                    '--seed','20261011'],cwd=RACINE/'assemblage/elm-review',env=env,check=True)
    for name,expected in [('conforme',None),('interdit','MrJam.Presentation'),('inutilise','NoUnused.Dependencies')]:
        r=subprocess.run([sys.executable,str(RACINE/'scripts/revoir-frontends.py'),
                          '--composant','style','--fixture',str(RACINE/'tests/fixtures'/('review-'+name))],
                         cwd=RACINE,env=env,capture_output=True,text=True)
        report=RACINE/'state/review-frontends'/('review-'+name+'.json')
        data=json.loads(report.read_text())
        if expected is None:
            if r.returncode:raise ValueError('Fixture conforme refusée : '+r.stdout[-1000:])
        else:
            rules={e['rule'] for f in data.get('errors',[]) for e in f.get('errors',[])}
            if r.returncode==0 or data.get('type')!='review-errors' or expected not in rules:
                raise ValueError('La commande canonique ne prouve pas le rejet par '+expected)
        # Ne pas écraser cette preuve avec le rapport de l'application suivante.
        (report.parent/('fixture-'+name+'.json')).write_text(report.read_text())
        print('Fixture '+name+' : résultat attendu vérifié avec la commande canonique.',flush=True)


if __name__=='__main__':main()
